using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Windows.Forms;
using RoboMaster.Workbench;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            bool preview=args.Contains("--preview");
            var connection=preview?null:Bootstrap.EnsureService();
            var control=new WorkbenchControl(connection==null?"":connection.url,connection==null?"":connection.token);
            if(preview) control.LoadPreviewState();
            int width=460;
            for(int i=0;i<args.Length-1;i++) if(args[i]=="--width") width=int.Parse(args[i+1]);
            var form=new Form { Text="RoboMaster 机械设计工作台 · API版 v1.0.0", ClientSize=new Size(width,940), MinimumSize=new Size(340,740), StartPosition=FormStartPosition.CenterScreen, BackColor=Color.White };
            control.Dock=DockStyle.Fill; form.Controls.Add(control);
            string screenshot=null;
            for(int i=0;i<args.Length-1;i++) if(args[i]=="--screenshot") screenshot=args[i+1];
            if(screenshot!=null)
            {
                var timer=new System.Windows.Forms.Timer { Interval=3500 };
                timer.Tick+=delegate
                {
                    timer.Stop();
                    using(var bitmap=new Bitmap(control.ClientSize.Width,control.ClientSize.Height)) { control.DrawToBitmap(bitmap,control.ClientRectangle); bitmap.Save(screenshot,System.Drawing.Imaging.ImageFormat.Png); }
                    timer.Dispose(); form.Close();
                };
                form.Shown+=delegate { timer.Start(); };
            }
            Application.Run(form); return 0;
        }
        catch(Exception ex)
        {
            if(args.Contains("--screenshot")) File.WriteAllText(Path.Combine(Bootstrap.Root,"data","preview-error.txt"),ex.ToString());
            else MessageBox.Show(ex.Message,"工作台启动失败",MessageBoxButtons.OK,MessageBoxIcon.Error);
            return 1;
        }
    }
}
