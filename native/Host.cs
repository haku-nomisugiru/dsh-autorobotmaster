using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swpublished;

[assembly: AssemblyTitle("RoboMaster Mechanical Workbench API Edition")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: ComVisible(false)]

namespace RoboMaster.Workbench
{
    public sealed class ServiceConnection
    {
        public string url { get; set; }
        public string token { get; set; }
        public int pid { get; set; }
    }
    public static class Bootstrap
    {
        public static readonly string Root = Path.GetFullPath(Path.Combine(Path.GetDirectoryName(typeof(Bootstrap).Assembly.Location), ".."));
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
        public static ServiceConnection EnsureService()
        {
            string manifest = Path.Combine(Root, "data", "runtime.json");
            var existing = ReadConnection(manifest);
            if (Healthy(existing)) return existing;
            string python = Path.Combine(Root, ".venv", "Scripts", "python.exe");
            string settings = Path.Combine(Root, "settings.json");
            if (File.Exists(settings))
            {
                var config = Json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(File.ReadAllText(settings));
                if (config.ContainsKey("python_executable")) python = Convert.ToString(config["python_executable"]);
            }
            if (!File.Exists(python)) throw new FileNotFoundException("未找到 Python，请检查 settings.json 中的 python_executable。", python);
            var info = new ProcessStartInfo(python, "\"" + Path.Combine(Root, "backend", "server.py") + "\"")
            {
                UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden,
                WorkingDirectory = Root
            };
            Process.Start(info);
            for (int i=0; i<60; i++)
            {
                Thread.Sleep(100);
                existing = ReadConnection(manifest);
                if (Healthy(existing)) return existing;
            }
            throw new InvalidOperationException("本地服务未能启动，请运行 diagnose.ps1 检查环境。");
        }
        private static ServiceConnection ReadConnection(string path)
        {
            try { return Json.Deserialize<ServiceConnection>(File.ReadAllText(path)); } catch { return null; }
        }
        private static bool Healthy(ServiceConnection connection)
        {
            if (connection == null || string.IsNullOrEmpty(connection.url) || string.IsNullOrEmpty(connection.token)) return false;
            Uri uri;
            if (!Uri.TryCreate(connection.url, UriKind.Absolute, out uri) || uri.Host != "127.0.0.1" || uri.Scheme != "http") return false;
            try
            {
                var request = (HttpWebRequest)WebRequest.Create(connection.url + "/api/settings");
                request.Proxy=null; request.Timeout=300; request.Headers["X-Workbench-Token"]=connection.token;
                using (var response=(HttpWebResponse)request.GetResponse()) return response.StatusCode == HttpStatusCode.OK;
            } catch { return false; }
        }
        public static void Context(ServiceConnection connection, string title, string path)
        {
            if (connection == null) return;
            var bytes=Encoding.UTF8.GetBytes(Json.Serialize(new { title=title, path=path }));
            var request=(HttpWebRequest)WebRequest.Create(connection.url+"/api/context");
            request.Proxy=null; request.Method="POST"; request.ContentType="application/json"; request.Timeout=1500;
            request.Headers["X-Workbench-Token"]=connection.token; request.ContentLength=bytes.Length;
            using (var output=request.GetRequestStream()) output.Write(bytes,0,bytes.Length);
            using (var response=request.GetResponse()) { }
        }
    }

    [ComVisible(true)]
    [Guid(AddinGuid)]
    [ProgId("RoboMaster.MechanicalWorkbench")]
    [ClassInterface(ClassInterfaceType.AutoDispatch)]
    public sealed class SwAddin : ISwAddin
    {
        public const string AddinGuid="C2A4DB56-4E3E-4B76-B95B-230C758417A1";
        private ISldWorks app;
        private SldWorks events;
        private ITaskpaneView pane;
        private WorkbenchControl control;
        private ServiceConnection connection;
        private System.Windows.Forms.Timer contextTimer;
        private bool callbackReady;
        private int eventCount;
        private string lastTitle="";

        [ComRegisterFunction]
        public static void Register(Type type)
        {
            using(var key=Registry.LocalMachine.CreateSubKey(@"SOFTWARE\SOLIDWORKS\Addins\{"+AddinGuid+"}"))
            {
                key.SetValue(null,0,RegistryValueKind.DWord);
                key.SetValue("Title","RoboMaster 机械设计工作台");
                key.SetValue("Description","API设置、设计对话、记忆与建模验收 · v1.0.0");
            }
            using(var key=Registry.CurrentUser.CreateSubKey(@"Software\SOLIDWORKS\AddInsStartup\{"+AddinGuid+"}")) key.SetValue(null,1,RegistryValueKind.DWord);
        }
        [ComUnregisterFunction]
        public static void Unregister(Type type)
        {
            Registry.LocalMachine.DeleteSubKeyTree(@"SOFTWARE\SOLIDWORKS\Addins\{"+AddinGuid+"}",false);
            Registry.CurrentUser.DeleteSubKeyTree(@"Software\SOLIDWORKS\AddInsStartup\{"+AddinGuid+"}",false);
        }
        public bool ConnectToSW(object thisSW, int cookie)
        {
            try
            {
                app=(ISldWorks)thisSW;
                callbackReady=app.SetAddinCallbackInfo2(0,this,cookie);
                if(!callbackReady) throw new InvalidOperationException("SolidWorks 回调初始化失败");
                connection=Bootstrap.EnsureService();
                string iconDirectory=Path.GetDirectoryName(typeof(SwAddin).Assembly.Location);
                int[] iconSizes={20,32,40,64,96,128};
                string[] icons=new string[iconSizes.Length];
                for(int i=0;i<iconSizes.Length;i++)
                {
                    icons[i]=Path.Combine(iconDirectory,"taskpane-"+iconSizes[i]+".png");
                    if(!File.Exists(icons[i])) throw new FileNotFoundException("缺少工作台图标，请重新构建或完整解压插件。",icons[i]);
                }
                pane=app.CreateTaskpaneView3(icons,"RoboMaster 机械设计工作台");
                if(pane==null) throw new InvalidOperationException("无法创建侧边栏");
                control=new WorkbenchControl(connection.url,connection.token);
                control.CreateControl();
                if(!pane.DisplayWindowFromHandlex64(control.Handle.ToInt64())) throw new InvalidOperationException("侧边栏控件未能加载");
                pane.ShowView();
                events=(SldWorks)app;
                events.ActiveModelDocChangeNotify+=OnDocumentChange;
                events.FileOpenPostNotify+=OnFileOpen;
                events.FileNewNotify2+=OnFileNew;
                contextTimer=new System.Windows.Forms.Timer { Interval=1800 };
                contextTimer.Tick+=delegate { UpdateContext(); };
                contextTimer.Start();
                Status("connected",null);
                return true;
            }
            catch(Exception ex) { Status("failed",ex.ToString()); Release(); return false; }
        }
        public bool DisconnectFromSW() { Release(); Status("disconnected",null); return true; }
        public void ShowWorkbench() { if(pane!=null) pane.ShowView(); }
        private int OnDocumentChange() { eventCount++; lastTitle=""; return 0; }
        private int OnFileOpen(string path) { eventCount++; lastTitle=""; return 0; }
        private int OnFileNew(object doc,int kind,string template) { eventCount++; lastTitle=""; return 0; }
        private void UpdateContext()
        {
            try
            {
                var model=app.IActiveDoc2;
                string title=model==null?"等待 SolidWorks 文档":model.GetTitle();
                if(title==lastTitle) return;
                lastTitle=title;
                string path=model==null?"":model.GetPathName();
                System.Threading.Tasks.Task.Run(delegate { try { Bootstrap.Context(connection,title,path); } catch { } });
                Status("connected",null);
            }
            catch(Exception ex) { Status("connected",ex.Message); }
        }
        private void Release()
        {
            if(contextTimer!=null) { contextTimer.Stop(); contextTimer.Dispose(); contextTimer=null; }
            if(events!=null)
            {
                try { events.ActiveModelDocChangeNotify-=OnDocumentChange; events.FileOpenPostNotify-=OnFileOpen; events.FileNewNotify2-=OnFileNew; } catch { }
                events=null;
            }
            if(pane!=null) { try { pane.DeleteView(); } catch { } pane=null; }
            if(control!=null) { control.Dispose(); control=null; }
            app=null;
        }
        private void Status(string status,string error)
        {
            try
            {
                string directory=Path.Combine(Bootstrap.Root,"data"); Directory.CreateDirectory(directory);
                string revision=app==null?null:app.RevisionNumber();
                File.WriteAllText(Path.Combine(directory,"addin-status.json"),new JavaScriptSerializer().Serialize(new {
                    status=status, callback_registered=callbackReady, taskpane_ready=pane!=null && control!=null,
                    solidworks_revision=revision, workbench_version=typeof(SwAddin).Assembly.GetName().Version.ToString(), event_count=eventCount, document=lastTitle, error=error,
                    at=DateTimeOffset.Now.ToString("o"), process_id=Process.GetCurrentProcess().Id
                }),Encoding.UTF8);
            } catch { }
        }
    }
}
