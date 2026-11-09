using System;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace RoboMaster.Workbench {
 public sealed class CadLibraryDialog : Form {
  readonly Func<string,string,object,Task<string>> request;
  readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 4194304 };
  readonly TextBox query = new TextBox { Dock=DockStyle.Fill };
  readonly ComboBox section = new ComboBox { Dock=DockStyle.Fill, DropDownStyle=ComboBoxStyle.DropDownList };
  readonly ListBox results = new ListBox { Dock=DockStyle.Fill };
  readonly TextBox detail = new TextBox { Dock=DockStyle.Fill, Multiline=true, ReadOnly=true, ScrollBars=ScrollBars.Vertical };
  readonly Button search = new Button { Text="检索", Dock=DockStyle.Fill };
  readonly Button download = new Button { Text="下载选中模型包", Dock=DockStyle.Fill, Enabled=false };
  readonly Button open = new Button { Text="打开已下载模型并检查", Dock=DockStyle.Fill, Enabled=false };
  readonly Button assessButton=new Button { Text="AI评估当前下载",Dock=DockStyle.Fill };
  readonly Button reportButton=new Button { Text="查看检查报告",Dock=DockStyle.Fill };
  readonly CheckBox entryOnly = new CheckBox { Text="仅下载入口文件（装配可能缺零件）", Dock=DockStyle.Fill };
  readonly Label status = new Label { Text="先检索已有模型，再评估来源和验证状态。", Dock=DockStyle.Fill, AutoEllipsis=true };
  bool busy;
  sealed class Item { public Dictionary<string,object> Value; public override string ToString() { return Convert.ToString(Value["name"]); } }
  public CadLibraryDialog(Func<string,string,object,Task<string>> send) {
   request=send; Text="RoboMaster 模型库"; Size=new Size(900,660); MinimumSize=new Size(650,450); StartPosition=FormStartPosition.CenterParent;
   var layout=new TableLayoutPanel { Dock=DockStyle.Fill, RowCount=6, ColumnCount=1, Padding=new Padding(12) };
   layout.RowStyles.Add(new RowStyle(SizeType.Absolute,36));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,30));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,36));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,36));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,60));
   var row=new TableLayoutPanel { Dock=DockStyle.Fill, ColumnCount=3 };row.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));row.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,140));row.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,80));
   section.Items.AddRange(new object[]{"全部（含补充）","云台","底盘","轮子或轮腿"});section.SelectedIndex=0;
   row.Controls.Add(query,0,0);row.Controls.Add(section,1,0);row.Controls.Add(search,2,0);
   var split=new SplitContainer { Dock=DockStyle.Fill, SplitterDistance=290 };split.Panel1.Controls.Add(results);split.Panel2.Controls.Add(detail);
   Shown += delegate { split.SplitterDistance = Math.Max(200, split.Width / 3); };
   layout.Controls.Add(row,0,0);layout.Controls.Add(split,0,1);layout.Controls.Add(entryOnly,0,2);layout.Controls.Add(download,0,3);var inspectionRow=new TableLayoutPanel { Dock=DockStyle.Fill,ColumnCount=3 };inspectionRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,44));inspectionRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,28));inspectionRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,28));
   reportButton.Click+=async delegate { try { ShowInspection(json.Deserialize<Dictionary<string,object>>(await request("GET","/api/library/inspection",null))); } catch(Exception e) { status.Text=e.Message; } };
   inspectionRow.Controls.Add(open,0,0);inspectionRow.Controls.Add(reportButton,1,0);
   assessButton.Click+=async delegate { await Assess(); };inspectionRow.Controls.Add(assessButton,2,0);layout.Controls.Add(inspectionRow,0,4);layout.Controls.Add(status,0,5);Controls.Add(layout);
   search.Click+=async delegate { await Search(); };download.Click+=async delegate { await Download(); };open.Click+=async delegate { await OpenInspect(); };results.SelectedIndexChanged+=delegate { ShowDetail(); };
   FormClosing+=delegate(object sender,FormClosingEventArgs e) { if(busy) { e.Cancel=true;status.Text="正在处理请求，请等待完成后关闭。"; } };
  }
  void SetBusy(bool value) { busy=value;search.Enabled=!value;results.Enabled=!value;download.Enabled=!value && results.SelectedItem!=null;entryOnly.Enabled=!value;assessButton.Enabled=!value;reportButton.Enabled=!value;open.Enabled=!value && results.SelectedItem!=null; }
  static string TextValue(Dictionary<string,object> d,string key) { object value;return d.TryGetValue(key,out value)&&value!=null?Convert.ToString(value):"未知"; }
  async Task Search() {
   SetBusy(true);status.Text="正在检索…";
   try {
    string[] ids={null,"gimbal","chassis","wheel_or_leg"};string url="/api/library/search?q="+Uri.EscapeDataString(query.Text.Trim());if(ids[section.SelectedIndex]!=null)url+="&section="+ids[section.SelectedIndex];
    var response=json.Deserialize<Dictionary<string,object>>(await request("GET",url,null));results.Items.Clear();detail.Clear();
    foreach(var item in (IEnumerable)response["items"])results.Items.Add(new Item { Value=(Dictionary<string,object>)item });
    status.Text="找到 "+results.Items.Count+" 个候选。文件可下载不表示已验证可装配。";if(results.Items.Count>0)results.SelectedIndex=0;
   } catch(Exception e) { status.Text="检索失败："+e.Message;results.Items.Clear();detail.Clear(); } finally { SetBusy(false); }
  }
  void ShowDetail() {
   var item=results.SelectedItem as Item;download.Enabled=!busy && item!=null;open.Enabled=!busy && item!=null;if(item==null)return;var m=item.Value;
   var text=new StringBuilder();text.AppendLine(TextValue(m,"name"));text.AppendLine("模型ID："+TextValue(m,"id"));text.AppendLine("来源："+TextValue(m,"source_url"));text.AppendLine("说明："+TextValue(m,"summary"));
   var checks=(Dictionary<string,object>)m["verification"];
   text.AppendLine("\r\n验证状态");
   foreach(var pair in new[]{new[]{"cad_parse_status","几何解析"},new[]{"native_mates_verified","原生配合"},new[]{"motion_verified","运动"},new[]{"fit_to_target_verified","目标适配"},new[]{"material_mass_verified","材料与质量"}}) {
    object value;checks.TryGetValue(pair[0],out value);text.AppendLine(pair[1]+"："+(value is bool?((bool)value?"已验证":"未验证"):Convert.ToString(value)));
   }
   var dependencies=(Dictionary<string,object>)m["dependency_scope"];
   text.AppendLine("\r\n装配依赖：尚未验证完整可加载");
   object countsObject;
   if(dependencies.TryGetValue("reference_counts",out countsObject) && countsObject is Dictionary<string,object>) {
    var counts=(Dictionary<string,object>)countsObject;
    foreach(var pair in new[]{new[]{"potential_local_match","潜在本地匹配"},new[]{"ambiguous","歧义引用"},new[]{"outside_asset","包外引用"}}) {
     object count;if(counts.TryGetValue(pair[0],out count))text.AppendLine(pair[1]+"："+count);
    }
   }text.AppendLine("\r\n限制：");foreach(var value in (IEnumerable)m["limitations"])text.AppendLine("• "+Convert.ToString(value));
   text.AppendLine("\r\n下载后可点击“打开已下载模型并检查”。使用独立工作副本，原生文件请求只读打开；STEP会导入新文档。检查仅覆盖当前配置。");detail.Text=text.ToString();
  }
  async Task Assess() {
   SetBusy(true);status.Text="正在基于实际结构与验证摘要评估复用条件…";
   try {
    var current=json.Deserialize<Dictionary<string,object>>(await request("POST","/api/library/assess",new { target_requirements="" }));
    for(int attempt=0;attempt<600;attempt++) {
     object value;if(current.TryGetValue("assessment",out value) && value is Dictionary<string,object>) {
      var assessment=(Dictionary<string,object>)value;
      if(TextValue(assessment,"status")!="running") {
       object result;if(assessment.TryGetValue("assessment",out result) && result is Dictionary<string,object>) {
        var resultMap=(Dictionary<string,object>)result;detail.AppendText("\r\n\r\nAI复用评估："+TextValue(resultMap,"summary")+"\r\n结论："+TextValue(resultMap,"decision")+"\r\n来源："+TextValue(assessment,"source_url")+"\r\n仍需验证："+json.Serialize(resultMap["missing_checks"]));
       } else detail.AppendText("\r\n评估未完成："+TextValue(assessment,"error"));
       status.Text="AI评估状态："+TextValue(assessment,"status");return;
      }
     }
     await Task.Delay(1000);current=json.Deserialize<Dictionary<string,object>>(await request("GET","/api/library/inspection",null));
    }
   } catch(Exception e) { status.Text="AI评估未完成："+e.Message; } finally { SetBusy(false); }
  }
  async Task OpenInspect() {
   var item=results.SelectedItem as Item;if(item==null)return;SetBusy(true);status.Text="正在准备工作副本并打开SolidWorks，随后读取依赖与组件结构…";
   try {
    var current=json.Deserialize<Dictionary<string,object>>(await request("POST","/api/library/open",new { id=TextValue(item.Value,"id") }));
    for(int attempt=0;attempt<900;attempt++) {
     string phase=TextValue(current,"status");
     if(phase!="preparing" && phase!="running")break;
     await Task.Delay(1000);current=json.Deserialize<Dictionary<string,object>>(await request("GET","/api/library/inspection",null));
    }
    ShowInspection(current);
   } catch(Exception e) { status.Text="打开检查未完成："+e.Message+"。可稍后点击查看检查报告。"; } finally { SetBusy(false); }
  }
  void ShowInspection(Dictionary<string,object> current) {
   var text=new StringBuilder();text.AppendLine("\r\n\r\n实际模型检查（依赖统计针对所选模型）："+TextValue(current,"status"));
   object reportObject;
   if(current.TryGetValue("report",out reportObject) && reportObject is Dictionary<string,object>) {
    var report=(Dictionary<string,object>)reportObject;
    object docObject;if(report.TryGetValue("document",out docObject) && docObject is Dictionary<string,object>) {
     var doc=(Dictionary<string,object>)docObject;text.AppendLine("文档："+TextValue(doc,"title"));text.AppendLine("路径："+TextValue(doc,"path"));
    }
    text.AppendLine("组件数："+TextValue(report,"component_count")+"；实体数："+TextValue(report,"body_count"));
    text.AppendLine("当前配置："+TextValue(report,"active_configuration"));
    object countsObject;if(report.TryGetValue("dependency_counts",out countsObject) && countsObject is Dictionary<string,object>) {
     var counts=(Dictionary<string,object>)countsObject;
     foreach(var pair in new[]{new[]{"missing_from_package","包内缺失引用"},new[]{"ambiguous","同名歧义引用"},new[]{"potential_local_match","仅同名候选"},new[]{"local_path_found","包内路径存在"}}) { object value;if(counts.TryGetValue(pair[0],out value))text.AppendLine(pair[1]+"："+value); }
    }
    text.AppendLine("\r\n所选模型缺失或歧义项（最多150条，完整包审计见报告）：");
    object issues;if(report.TryGetValue("dependency_issues",out issues) && issues is IEnumerable)foreach(var value in (IEnumerable)issues) {
     var issue=value as Dictionary<string,object>;if(issue!=null)text.AppendLine(TextValue(issue,"status")+" | "+TextValue(issue,"saved_path")+" | 引用方："+TextValue(issue,"owner"));
    }
    text.AppendLine("\r\n实际组件结构（最多150项）：");
    object components;if(report.TryGetValue("components",out components) && components is IEnumerable)foreach(var value in (IEnumerable)components) {
     var component=value as Dictionary<string,object>;if(component!=null)text.AppendLine(TextValue(component,"name")+"；父级="+TextValue(component,"parent")+"；加载="+TextValue(component,"loaded")+"；抑制状态="+TextValue(component,"suppression")+"；路径="+TextValue(component,"path"));
    }
    foreach(string key in new[]{"dependency_errors","structure_errors","unloaded_components","external_components","limitations"}) {
     object values;if(report.TryGetValue(key,out values) && values!=null)text.AppendLine(key+"："+json.Serialize(values));
    }
    if(report.ContainsKey("error"))text.AppendLine("错误："+TextValue(report,"error"));
   }
   if(current.ContainsKey("error"))text.AppendLine("错误："+TextValue(current,"error"));
   text.AppendLine("完整报告："+TextValue(current,"report_path"));detail.AppendText(text.ToString());
   status.Text=TextValue(current,"status")=="inspected"?"已读取模型结构与依赖，AI后续评估会使用这些证据；配合、运动与适配仍待验证。":"检查状态："+TextValue(current,"status")+"。已保留部分证据，请查看详情。";
  }
  async Task Download() {
   var item=results.SelectedItem as Item;if(item==null)return;SetBusy(true);status.Text="正在下载并核对SHA-256，大模型包可能需要数分钟…";
   try {
    var result=json.Deserialize<Dictionary<string,object>>(await request("POST","/api/library/download",new { id=TextValue(item.Value,"id"),kind=entryOnly.Checked?"file":"package" }));
    detail.AppendText("\r\n\r\n已下载："+TextValue(result,"path")+"\r\nSHA-256："+TextValue(result,"sha256"));
    status.Text="文件校验通过。"+(TextValue(result,"attached_to_current_task")=="True"?"已加入当前任务，继续发送设计要求即可引用。":"当前任务已变化，请在当前任务重新选择参考。");
   } catch(Exception e) { status.Text="下载失败："+e.Message; } finally { SetBusy(false); }
  }
 }
}
