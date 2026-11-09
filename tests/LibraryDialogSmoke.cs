using System;
using System.Drawing;
using System.IO;
using System.Net;
using System.Reflection;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Collections.Generic;
using System.Windows.Forms;
using RoboMaster.Workbench;
class Smoke {
 [STAThread] static void Main() {
  using(var dialog=new CadLibraryDialog((method,path,body)=>Task.FromResult("{}"))) {
   dialog.StartPosition=FormStartPosition.Manual;dialog.Location=new Point(-10000,-10000);dialog.ShowInTaskbar=false;dialog.Show();Application.DoEvents();
   var req=(HttpWebRequest)WebRequest.Create("http://127.0.0.1:8765/v1/search?q=swerve&section=wheel_or_leg");req.Proxy=null;
   string text;using(var response=req.GetResponse())using(var reader=new StreamReader(response.GetResponseStream()))text=reader.ReadToEnd();
   var parsed=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(text);
   var type=dialog.GetType();var list=(ListBox)type.GetField("results",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(dialog);
   var itemType=type.GetNestedType("Item",BindingFlags.NonPublic);
   foreach(var model in (System.Collections.IEnumerable)parsed["items"]) { var item=Activator.CreateInstance(itemType,true);itemType.GetField("Value").SetValue(item,model);list.Items.Add(item); }
   if(list.Items.Count==0)throw new Exception("No candidates");list.SelectedIndex=0;Application.DoEvents();
   var detail=(TextBox)type.GetField("detail",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(dialog);
   if(!detail.Text.Contains("https://bbs.robomaster.com") || !detail.Text.Contains("未验证"))throw new Exception("Missing source or status");
   using(var bitmap=new Bitmap(dialog.Width,dialog.Height)) { dialog.DrawToBitmap(bitmap,new Rectangle(0,0,dialog.Width,dialog.Height));bitmap.Save(Path.Combine(Bootstrap.Root,"docs","library-dialog.png")); }
   dialog.Close();Console.WriteLine("Native dialog with actual CAD source and verification passed.");
  }
 }
}
