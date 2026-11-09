using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace RoboMaster.Workbench
{
    public sealed class KnowledgeDialog : Form
    {
        private static readonly Color Ink = WorkbenchTheme.Ink, Muted = WorkbenchTheme.Muted, Accent = WorkbenchTheme.Accent, Surface = WorkbenchTheme.Surface;
        private readonly string baseUrl, token;
        private readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 8*1024*1024 };
        private readonly HashSet<HttpWebRequest> requests = new HashSet<HttpWebRequest>();
        private readonly System.Windows.Forms.Timer timer;
        private readonly Label stats, status, historyTitle, skillTitle;
        private readonly TextBox summaryText, sessionText, skillText;
        private readonly TextBox noteInput, notePreview;
        private readonly ComboBox noteScope;
        private readonly ListView notes, sessions, skills;
        private readonly Button summarize, generate, addNote, deleteNote, toggle, directory, refresh;
        private readonly TabControl tabs;
        private KnowledgeSnapshot snapshot;
        private string fingerprint = "", skillPath;
        private bool disposed, polling, posting, rendering;
        private int sessionSequence, skillSequence;
        private DateTime noticeUntil = DateTime.MinValue;

        public KnowledgeDialog(string baseUrl, string token)
        {
            this.baseUrl=(baseUrl??"").TrimEnd('/'); this.token=token??"";
            Text="记忆与 Skill — RoboMaster"; Font=new Font("Microsoft YaHei UI",9f); ForeColor=Ink; BackColor=Surface;
            ClientSize=new Size(820,680); MinimumSize=new Size(680,550); StartPosition=FormStartPosition.CenterParent;
            ShowInTaskbar=false; AutoScaleMode=AutoScaleMode.Dpi;
            var root=new TableLayoutPanel { Dock=DockStyle.Fill, ColumnCount=1, RowCount=4, Margin=Padding.Empty };
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute,73)); root.RowStyles.Add(new RowStyle(SizeType.Absolute,45));
            root.RowStyles.Add(new RowStyle(SizeType.Percent,100)); root.RowStyles.Add(new RowStyle(SizeType.Absolute,43));
            Controls.Add(root);
            var header=new Panel { Dock=DockStyle.Fill, Margin=Padding.Empty, BackColor=WorkbenchTheme.Header };
            var pixelIcon=new PixelIconControl { Light=true,Location=new Point(20,18),Size=new Size(20,20),BackColor=Color.Transparent,AccessibleName="RoboMaster 像素图标" };
            var title=new Label { Text="记忆与 Skill",Font=new Font(Font.FontFamily,15f,FontStyle.Bold),ForeColor=Color.White,AutoSize=true,Location=new Point(50,12) };
            var subtitle=new Label { Text="保存设计决定与项目经验，让下一次设计接着进行。",ForeColor=WorkbenchTheme.HeaderMuted,AutoSize=true,Font=new Font(Font.FontFamily,8f),Location=new Point(20,43) };
            stats=new Label { Text="正在读取记录…",ForeColor=WorkbenchTheme.HeaderMuted,Size=new Size(260,24),TextAlign=ContentAlignment.MiddleRight,Anchor=AnchorStyles.Right|AnchorStyles.Top,Location=new Point(540,20) };
            header.Resize+=delegate { stats.Left=header.ClientSize.Width-stats.Width-18; };
            header.Controls.AddRange(new Control[]{pixelIcon,title,subtitle,stats}); root.Controls.Add(header,0,0);
            var toolbar=new FlowLayoutPanel { Dock=DockStyle.Fill,WrapContents=false,Padding=new Padding(15,7,8,4),Margin=Padding.Empty };
            summarize=MakeButton("总结当前任务",true,116); summarize.Name="knowledge.summarize";
            generate=MakeButton("生成 / 更新 Skill",false,145); generate.Name="knowledge.generate";
            refresh=MakeButton("刷新",false,68);
            summarize.Click+=async delegate { await Post("/api/knowledge/summarize",new {},"已提交，正在总结当前任务…"); };
            generate.Click+=async delegate { await Post("/api/knowledge/skill",new {},"已提交，正在整理 Skill…"); };
            refresh.Click+=async delegate { await RefreshKnowledgeAsync(); };
            toolbar.Controls.AddRange(new Control[]{summarize,generate,refresh}); root.Controls.Add(toolbar,0,1);
            tabs=new TabControl { Dock=DockStyle.Fill,Margin=new Padding(15,3,15,0),Name="knowledge.tabs",DrawMode=TabDrawMode.OwnerDrawFixed };
            tabs.DrawItem+=delegate(object sender,DrawItemEventArgs e)
            {
                Rectangle bounds=tabs.GetTabRect(e.Index);
                using(var brush=new SolidBrush(e.Index==tabs.SelectedIndex?Color.White:Surface))e.Graphics.FillRectangle(brush,bounds);
                using(var pen=new Pen(WorkbenchTheme.Border))e.Graphics.DrawRectangle(pen,bounds.X,bounds.Y,Math.Max(0,bounds.Width-1),Math.Max(0,bounds.Height-1));
                TextRenderer.DrawText(e.Graphics,tabs.TabPages[e.Index].Text,tabs.Font,bounds,Ink,TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter|TextFormatFlags.NoPrefix|TextFormatFlags.SingleLine);
            };
            root.Controls.Add(tabs,0,2);

            var memory=Page("记忆"); tabs.TabPages.Add(memory);
            var memorySplit=Split(390,250,260); memory.Controls.Add(memorySplit);
            summaryText=Preview("当前任务还没有摘要。\n\n点击“总结当前任务”，整理设计决定、未完成事项和建模经验。");
            memorySplit.Panel1.Controls.Add(summaryText); memorySplit.Panel1.Controls.Add(Caption("当前任务摘要"));
            notes=MakeList("knowledge.notes",new[]{"内容","范围","时间"},new[]{175,52,100});
            notePreview=new TextBox { Dock=DockStyle.Bottom,Height=58,Multiline=true,ReadOnly=true,BorderStyle=BorderStyle.FixedSingle,BackColor=Surface,ScrollBars=ScrollBars.Vertical,Text="选择一条备注可查看全文。" };
            notes.SelectedIndexChanged+=delegate { var n=Selected<KnowledgeNote>(notes); notePreview.Text=n==null?"选择一条备注可查看全文。":n.text??""; UpdateButtons(); };
            var composer=new Panel { Dock=DockStyle.Bottom,Height=126,Padding=new Padding(0,7,0,0) };
            noteInput=new TextBox { Dock=DockStyle.Fill,Multiline=true,ScrollBars=ScrollBars.Vertical,MaxLength=8000,Name="knowledge.note.input",BackColor=Color.White,ForeColor=Ink };
            noteInput.TextChanged+=delegate { UpdateButtons(); };
            var scopeRow=new FlowLayoutPanel { Dock=DockStyle.Bottom,Height=32,WrapContents=false,Padding=new Padding(0,4,0,0) };
            noteScope=new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList,Width=106,Name="knowledge.note.scope",BackColor=Color.White,ForeColor=Ink,DrawMode=DrawMode.OwnerDrawFixed,FlatStyle=FlatStyle.Flat };
            noteScope.DrawItem+=delegate(object sender,DrawItemEventArgs e)
            {
                if(e.Index<0)return;
                bool selected=(e.State&DrawItemState.Selected)!=0;
                Color background=selected?WorkbenchTheme.Selection:Color.White;
                using(var brush=new SolidBrush(background))e.Graphics.FillRectangle(brush,e.Bounds);
                Rectangle bounds=e.Bounds;bounds.Inflate(-4,0);
                TextRenderer.DrawText(e.Graphics,Convert.ToString(noteScope.Items[e.Index]),noteScope.Font,bounds,Ink,TextFormatFlags.Left|TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis|TextFormatFlags.NoPrefix|TextFormatFlags.SingleLine);
                if((e.State&DrawItemState.Focus)!=0)ControlPaint.DrawFocusRectangle(e.Graphics,e.Bounds,Ink,background);
            };
            noteScope.Items.AddRange(new object[]{"仅此项目","通用备注"}); noteScope.SelectedIndex=0;
            addNote=MakeButton("添加备注",true,90); addNote.Name="knowledge.note.add";
            addNote.Click+=async delegate { string text=noteInput.Text.Trim(); if(text.Length==0)return; if(await Post("/api/knowledge/note",new {text=text,scope=noteScope.SelectedIndex==1?"global":"project"},"备注已保存")&&!disposed)noteInput.Clear(); };
            scopeRow.Controls.AddRange(new Control[]{noteScope,addNote});
            var deleteRow=new FlowLayoutPanel { Dock=DockStyle.Bottom,Height=32,WrapContents=false,Padding=new Padding(0,3,0,0) };
            deleteNote=MakeButton("删除选中备注",false,120); deleteNote.Name="knowledge.note.delete";
            deleteNote.Click+=async delegate { var n=Selected<KnowledgeNote>(notes); if(n!=null)await Post("/api/knowledge/forget",new {id=n.id},"备注已删除"); };
            deleteRow.Controls.Add(deleteNote);
            composer.Controls.Add(noteInput); composer.Controls.Add(scopeRow); composer.Controls.Add(deleteRow);
            composer.Controls.SetChildIndex(noteInput,0); composer.Controls.SetChildIndex(scopeRow,1); composer.Controls.SetChildIndex(deleteRow,2);
            var noteTitle=Caption("手动备注");
            memorySplit.Panel2.Controls.Add(notes); memorySplit.Panel2.Controls.Add(notePreview); memorySplit.Panel2.Controls.Add(composer); memorySplit.Panel2.Controls.Add(noteTitle);
            memorySplit.Panel2.Controls.SetChildIndex(notes,0); memorySplit.Panel2.Controls.SetChildIndex(notePreview,1);
            memorySplit.Panel2.Controls.SetChildIndex(composer,2); memorySplit.Panel2.Controls.SetChildIndex(noteTitle,3);

            var history=Page("历史"); tabs.TabPages.Add(history);
            var historySplit=Split(280,200,300); history.Controls.Add(historySplit);
            sessions=MakeList("knowledge.sessions",new[]{"任务","最近更新"},new[]{170,100});
            sessions.SelectedIndexChanged+=async delegate { if(rendering)return;var item=Selected<KnowledgeSession>(sessions);if(item!=null)await LoadSession(item.project_id); };
            historySplit.Panel1.Controls.Add(sessions); historySplit.Panel1.Controls.Add(Caption("保存的任务"));
            sessionText=Preview("选择左侧任务，查看摘要和对话。"); historyTitle=Caption("任务记录");
            historySplit.Panel2.Controls.Add(sessionText); historySplit.Panel2.Controls.Add(historyTitle);

            var skillPage=Page("Skill"); tabs.TabPages.Add(skillPage);
            var skillSplit=Split(280,200,300); skillPage.Controls.Add(skillSplit);
            skills=MakeList("knowledge.skills",new[]{"Skill","状态","版本"},new[]{160,55,55});
            skills.SelectedIndexChanged+=async delegate { if(rendering)return;skillPath=null;UpdateButtons();var item=Selected<KnowledgeSkill>(skills);if(item!=null)await LoadSkill(item.id); };
            skillSplit.Panel1.Controls.Add(skills); skillSplit.Panel1.Controls.Add(Caption("可用 Skill"));
            skillText=Preview("选择左侧 Skill 查看正文。\n\n点击“生成 / 更新 Skill”，从当前任务中整理可复用经验。"); skillText.Font=new Font("Consolas",9f);
            skillTitle=Caption("Skill 正文");
            var skillActions=new FlowLayoutPanel { Dock=DockStyle.Bottom,Height=38,WrapContents=false,Padding=new Padding(0,5,0,0) };
            toggle=MakeButton("启用 Skill",true,115);toggle.Name="knowledge.skill.toggle";
            directory=MakeButton("打开所在目录",false,120);
            toggle.Click+=async delegate { var item=Selected<KnowledgeSkill>(skills);if(item!=null)await Post("/api/knowledge/toggle",new {id=item.id,enabled=!item.enabled},item.enabled?"Skill 已停用":"Skill 已启用"); };
            directory.Click+=delegate { OpenDirectory(); };
            skillActions.Controls.AddRange(new Control[]{toggle,directory});
            skillSplit.Panel2.Controls.Add(skillText);skillSplit.Panel2.Controls.Add(skillActions);skillSplit.Panel2.Controls.Add(skillTitle);
            skillSplit.Panel2.Controls.SetChildIndex(skillText,0);skillSplit.Panel2.Controls.SetChildIndex(skillActions,1);skillSplit.Panel2.Controls.SetChildIndex(skillTitle,2);
            var bottom=new Panel { Dock=DockStyle.Fill,Margin=Padding.Empty,Padding=new Padding(17,9,16,6) };
            status=new Label { Text="正在连接本地记录…",Dock=DockStyle.Fill,AutoEllipsis=true,ForeColor=Muted,TextAlign=ContentAlignment.MiddleLeft,Name="knowledge.status" };
            var close=MakeButton("关闭",false,66);close.Dock=DockStyle.Right;close.Click+=delegate {Close();};
            bottom.Controls.Add(status);bottom.Controls.Add(close);root.Controls.Add(bottom,0,3);
            timer=new System.Windows.Forms.Timer {Interval=1500};timer.Tick+=async delegate {await RefreshKnowledgeAsync();};
            Shown+=async delegate {timer.Start();await RefreshKnowledgeAsync();}; UpdateButtons();
        }

        private TabPage Page(string text) {return new TabPage(text){BackColor=Color.White,Padding=new Padding(10),UseVisualStyleBackColor=false};}
        private SplitContainer Split(int distance,int left,int right) {return new SplitContainer {Dock=DockStyle.Fill,Orientation=Orientation.Vertical,SplitterWidth=7,BackColor=Surface,Size=new Size(780,440),Panel1MinSize=left,Panel2MinSize=right,SplitterDistance=distance};}
        private Label Caption(string text) {return new Label {Text=text,Dock=DockStyle.Top,Height=29,Padding=new Padding(2,3,0,0),Font=new Font(Font,FontStyle.Bold),ForeColor=Ink,BackColor=Color.White,AutoEllipsis=true};}

        private TextBox Preview(string text) {return new TextBox {Text=Lines(text),Dock=DockStyle.Fill,Multiline=true,ReadOnly=true,BorderStyle=BorderStyle.None,BackColor=Color.White,ForeColor=Ink,Font=new Font(Font.FontFamily,9f),WordWrap=true,ScrollBars=ScrollBars.Vertical,MaxLength=int.MaxValue};}
        private Button MakeButton(string text,bool primary,int width)
        {
            var b=new Button {Text=text,Width=width,Height=29,FlatStyle=FlatStyle.Flat,Cursor=Cursors.Hand,Font=new Font(Font.FontFamily,8.3f),BackColor=primary?Accent:Color.White,ForeColor=primary?Color.White:Ink,Margin=new Padding(0,0,7,0),UseVisualStyleBackColor=false};
            b.FlatAppearance.BorderSize=primary?0:1;b.FlatAppearance.BorderColor=WorkbenchTheme.Border;
            b.FlatAppearance.MouseOverBackColor=primary?WorkbenchTheme.Ink:Surface;
            b.FlatAppearance.MouseDownBackColor=primary?WorkbenchTheme.Header:WorkbenchTheme.Selection;
            b.EnabledChanged+=delegate {
                b.BackColor=primary?(b.Enabled?Accent:WorkbenchTheme.Selection):Color.White;
                b.ForeColor=b.Enabled?(primary?Color.White:Ink):Muted;
            };
            return b;
        }
        private ListView MakeList(string name,string[] headings,int[] widths)
        {
            var list=new ListView {Name=name,Dock=DockStyle.Fill,View=View.Details,FullRowSelect=true,MultiSelect=false,HideSelection=false,BorderStyle=BorderStyle.FixedSingle,Font=new Font(Font.FontFamily,8.3f),BackColor=Color.White,ForeColor=Ink,OwnerDraw=true};
            list.DrawColumnHeader+=delegate(object sender,DrawListViewColumnHeaderEventArgs e)
            {
                using(var brush=new SolidBrush(Surface))e.Graphics.FillRectangle(brush,e.Bounds);
                using(var pen=new Pen(WorkbenchTheme.Border))e.Graphics.DrawRectangle(pen,e.Bounds.X,e.Bounds.Y,Math.Max(0,e.Bounds.Width-1),Math.Max(0,e.Bounds.Height-1));
                Rectangle bounds=e.Bounds;bounds.Inflate(-5,0);
                TextRenderer.DrawText(e.Graphics,e.Header.Text,list.Font,bounds,Ink,TextFormatFlags.Left|TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis|TextFormatFlags.NoPrefix|TextFormatFlags.SingleLine);
            };
            list.DrawItem+=delegate(object sender,DrawListViewItemEventArgs e)
            {
                if(list.View!=View.Details){e.DrawDefault=true;return;}
                using(var brush=new SolidBrush(e.Item.Selected?WorkbenchTheme.Selection:Color.White))e.Graphics.FillRectangle(brush,e.Bounds);
            };
            list.DrawSubItem+=delegate(object sender,DrawListViewSubItemEventArgs e)
            {
                Color background=e.Item.Selected?WorkbenchTheme.Selection:Color.White;
                using(var brush=new SolidBrush(background))e.Graphics.FillRectangle(brush,e.Bounds);
                Rectangle bounds=e.Bounds;bounds.Inflate(-5,0);
                TextRenderer.DrawText(e.Graphics,e.SubItem.Text,list.Font,bounds,Ink,TextFormatFlags.Left|TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis|TextFormatFlags.NoPrefix|TextFormatFlags.SingleLine);
                if(e.ColumnIndex==0&&e.Item.Focused&&list.Focused)ControlPaint.DrawFocusRectangle(e.Graphics,e.Bounds,Ink,background);
            };
            list.SelectedIndexChanged+=delegate {list.Invalidate();};
            list.GotFocus+=delegate {list.Invalidate();};list.LostFocus+=delegate {list.Invalidate();};
            for(int i=0;i<headings.Length;i++)list.Columns.Add(headings[i],widths[i]);return list;
        }
        private static T Selected<T>(ListView list) where T:class {return list!=null&&list.SelectedItems.Count>0?list.SelectedItems[0].Tag as T:null;}
        private static string DateLabel(string raw) {DateTimeOffset d;return DateTimeOffset.TryParse(raw,out d)?d.ToOffset(TimeSpan.FromHours(8)).ToString("MM-dd HH:mm"):"";}
        private static string ScopeLabel(string value) {return value=="global"?"通用":"此项目";}

        public async Task RefreshKnowledgeAsync()
        {
            if(disposed||polling||string.IsNullOrWhiteSpace(baseUrl))return;polling=true;
            try
            {
                string response=await Request("GET","/api/knowledge",null);if(disposed)return;
                var next=json.Deserialize<KnowledgeSnapshot>(response);if(next==null)throw new InvalidDataException("没有读到项目记录。");
                snapshot=next;string signature=json.Serialize(new {next.project_id,next.summary,next.notes,next.sessions,next.skills});
                if(signature!=fingerprint){fingerprint=signature;RenderSnapshot(next);}
                if(next.stats!=null)stats.Text=string.Format("{0} 个任务  ·  {1} 条备注  ·  {2} 个 Skill",next.stats.sessions,next.stats.notes,next.stats.skills);
                bool busy=next.learning!=null&&next.learning.busy;
                if(next.learning!=null&&!string.IsNullOrWhiteSpace(next.learning.error))ShowStatus("整理未完成："+next.learning.error,true);
                else if(DateTime.UtcNow < noticeUntil) { }
                else if(busy)ShowStatus("正在总结与整理经验…  关闭窗口后仍会继续。",false);
                else ShowStatus(LearningLabel(next.learning==null?"":next.learning.status),false);
                UpdateButtons();
            }
            catch(Exception ex){if(!disposed)ShowStatus("记录读取失败："+Friendly(ex),true);}
            finally{polling=false;}
        }
        private void RenderSnapshot(KnowledgeSnapshot next)
        {
            var oldNote=Selected<KnowledgeNote>(notes);var oldSession=Selected<KnowledgeSession>(sessions);var oldSkill=Selected<KnowledgeSkill>(skills);
            string noteId=oldNote==null?null:oldNote.id,sessionId=oldSession==null?null:oldSession.project_id,skillId=oldSkill==null?null:oldSkill.id;
            rendering=true;
            try
            {
                summaryText.Text=Lines(FormatSummary(next.summary));
                notes.BeginUpdate();notes.Items.Clear();
                if(next.notes!=null)foreach(var n in next.notes){var row=new ListViewItem(new[]{OneLine(n.text),ScopeLabel(n.scope),DateLabel(n.created_at)}){Tag=n};notes.Items.Add(row);if(n.id==noteId)row.Selected=true;}notes.EndUpdate();
                sessions.BeginUpdate();sessions.Items.Clear();
                if(next.sessions!=null)foreach(var s in next.sessions){var row=new ListViewItem(new[]{string.IsNullOrWhiteSpace(s.title)?"未命名任务":s.title,DateLabel(s.updated_at)}){Tag=s};sessions.Items.Add(row);if(s.project_id==sessionId)row.Selected=true;}sessions.EndUpdate();
                skills.BeginUpdate();skills.Items.Clear();
                if(next.skills!=null)foreach(var s in next.skills){var row=new ListViewItem(new[]{string.IsNullOrWhiteSpace(s.title)?s.name:s.title,s.enabled?"已启用":"已停用",s.version??""}){Tag=s};skills.Items.Add(row);if(s.id==skillId)row.Selected=true;}skills.EndUpdate();
                if(sessions.SelectedItems.Count==0&&sessions.Items.Count>0)sessions.Items[0].Selected=true;
                if(skills.SelectedItems.Count==0&&skills.Items.Count>0)skills.Items[0].Selected=true;
                var selectedNote=Selected<KnowledgeNote>(notes);notePreview.Text=selectedNote==null?"选择一条备注可查看全文。":selectedNote.text??"";
                if(skills.Items.Count==0){skillSequence++;skillPath=null;skillTitle.Text="Skill 正文";skillText.Text="还没有可用的 Skill。\n\n完成任务后，点击“生成 / 更新 Skill”整理可复用经验。";}
                if(sessions.Items.Count==0){sessionSequence++;historyTitle.Text="任务记录";sessionText.Text="还没有保存的任务记录。";}
            }
            finally{rendering=false;}
            var selectedSession=Selected<KnowledgeSession>(sessions);var selectedSkill=Selected<KnowledgeSkill>(skills);
            if(selectedSession!=null)Observe(LoadSession(selectedSession.project_id));
            if(selectedSkill!=null)Observe(LoadSkill(selectedSkill.id));
        }
        private async void Observe(Task task){try{await task;}catch(Exception ex){if(!disposed)ShowStatus(Friendly(ex),true);}}
        private async Task LoadSession(string id)
        {
            int sequence=++sessionSequence;
            try
            {
                string response=await Request("GET","/api/knowledge/session?id="+Uri.EscapeDataString(id??""),null);
                if(disposed||sequence!=sessionSequence)return;
                var s=json.Deserialize<KnowledgeSessionDetail>(response);if(s==null)throw new InvalidDataException("任务记录为空。");
                historyTitle.Text=string.IsNullOrWhiteSpace(s.title)?"任务记录":s.title;var content=new StringBuilder();
                if(s.summary!=null)content.AppendLine(FormatSummaryObject(s.summary)).AppendLine();
                content.AppendLine("对话记录").AppendLine();
                if(s.messages!=null)foreach(var m in s.messages){content.AppendLine((m.role=="user"?"你":m.role=="assistant"?"设计助手":"项目记录")+"  "+DateLabel(m.at));content.AppendLine(m.content??"").AppendLine();}
                sessionText.Text=Lines(content.ToString());
            }
            catch(Exception ex){if(!disposed&&sequence==sessionSequence){sessionText.Text="未能读取这份记录。";ShowStatus(Friendly(ex),true);}}
        }
        private async Task LoadSkill(string id)
        {
            int sequence=++skillSequence;
            try
            {
                string response=await Request("GET","/api/knowledge/skill?id="+Uri.EscapeDataString(id??""),null);
                if(disposed||sequence!=skillSequence)return;
                var d=json.Deserialize<KnowledgeSkillDetail>(response);if(d==null)throw new InvalidDataException("Skill 正文为空。");
                skillText.Text=Lines(d.content??"正文暂为空。");var selected=Selected<KnowledgeSkill>(skills);
                skillTitle.Text=selected!=null&&!string.IsNullOrWhiteSpace(selected.title)?selected.title:d.name??"Skill 正文";skillPath=d.path;UpdateButtons();
            }
            catch(Exception ex){if(!disposed&&sequence==skillSequence){skillPath=null;skillText.Text="未能读取这份 Skill。";ShowStatus(Friendly(ex),true);UpdateButtons();}}
        }
        private async Task<bool> Post(string path,object body,string submitted)
        {
            if(disposed||posting)return false;posting=true;UpdateButtons();
            try{await Request("POST",path,body);if(disposed)return false;ShowStatus(submitted,false);await RefreshKnowledgeAsync();return true;}
            catch(Exception ex){if(!disposed)ShowStatus(Friendly(ex),true);return false;}
            finally{posting=false;if(!disposed)UpdateButtons();}
        }
        private async Task<string> Request(string method,string path,object payload)
        {
            var r=(HttpWebRequest)WebRequest.Create(baseUrl+path);r.Method=method;r.Proxy=null;r.Timeout=6000;r.ReadWriteTimeout=6000;r.Headers["X-Workbench-Token"]=token;
            lock(requests)requests.Add(r);
            using(var deadline=new System.Threading.CancellationTokenSource())
            using(deadline.Token.Register(delegate{try{r.Abort();}catch{}}))
            {
                deadline.CancelAfter(6000);
                try
                {
                    if(payload!=null){byte[] bytes=Encoding.UTF8.GetBytes(json.Serialize(payload));r.ContentType="application/json; charset=utf-8";r.ContentLength=bytes.Length;using(Stream stream=await r.GetRequestStreamAsync()){await stream.WriteAsync(bytes,0,bytes.Length);}}
                    using(var response=(HttpWebResponse)await r.GetResponseAsync())
                    using(var reader=new StreamReader(response.GetResponseStream(),Encoding.UTF8)){return await reader.ReadToEndAsync();}
                }
                catch(WebException ex)
                {
                    if(ex.Response!=null)
                    {
                        using(var response=ex.Response)
                        using(var reader=new StreamReader(response.GetResponseStream(),Encoding.UTF8))
                        {
                            string body=await reader.ReadToEndAsync();Dictionary<string,object> error=null;
                            try{error=json.Deserialize<Dictionary<string,object>>(body);}catch{}
                            if(error!=null&&error.ContainsKey("error"))throw new InvalidOperationException(Convert.ToString(error["error"]));
                        }
                    }
                    if(deadline.IsCancellationRequested)throw new TimeoutException("本地记录服务响应超时，请稍后刷新。");throw;
                }
                finally{lock(requests)requests.Remove(r);}
            }
        }
        private void UpdateButtons()
        {
            bool ready=snapshot!=null&&!posting&&!disposed,learning=snapshot!=null&&snapshot.learning!=null&&snapshot.learning.busy;
            summarize.Enabled=generate.Enabled=ready&&!learning;refresh.Enabled=!posting&&!disposed;
            if(addNote!=null)addNote.Enabled=ready&&noteInput!=null&&noteInput.Text.Trim().Length>0;
            if(deleteNote!=null)deleteNote.Enabled=ready&&Selected<KnowledgeNote>(notes)!=null;
            if(toggle!=null){var s=Selected<KnowledgeSkill>(skills);toggle.Enabled=ready&&s!=null;toggle.Text=s!=null&&s.enabled?"停用 Skill":"启用 Skill";}
            if(directory!=null)directory.Enabled=!disposed&&!string.IsNullOrWhiteSpace(skillPath);
        }
        private void OpenDirectory()
        {

            try{if(string.IsNullOrWhiteSpace(skillPath))return;string dir=Directory.Exists(skillPath)?skillPath:Path.GetDirectoryName(skillPath);if(string.IsNullOrWhiteSpace(dir)||!Directory.Exists(dir))throw new DirectoryNotFoundException("Skill 所在目录暂不可用。");Process.Start(new ProcessStartInfo("explorer.exe","\""+dir+"\""){UseShellExecute=true});}
            catch(Exception ex){ShowStatus(Friendly(ex),true);}
        }
        private static string Lines(string s){return(s??"").Replace("\r\n","\n").Replace("\n","\r\n");}
        private static string OneLine(string s){return(s??"").Replace("\r"," ").Replace("\n"," ");}
        private static string Friendly(Exception ex){string s=ex is WebException?"本地记录服务暂时不可用，请稍后刷新。":ex.Message??"操作未完成。";return s.Length>420?s.Substring(0,420):s;}
        private void ShowStatus(string text,bool error){status.Text=text;status.ForeColor=error?Ink:Muted;if(error)noticeUntil=DateTime.UtcNow.AddSeconds(12);}
        private static string LearningLabel(string s)
        {
            if(string.IsNullOrWhiteSpace(s)||s=="idle"||s=="ready")return"记录已同步。可继续建模，或在这里整理经验。";
            if(s=="completed"||s=="done")return"整理已完成，记录和 Skill 已刷新。";
            foreach(char c in s)if(c>127)return s;return"记录已同步。";
        }
        private string FormatSummaryObject(object value){if(value is string)return(string)value;try{return FormatSummary(json.Deserialize<KnowledgeSummary>(json.Serialize(value)));}catch{return"暂无摘要。";}}
        private static string FormatSummary(KnowledgeSummary s)
        {
            if(s==null)return"当前任务还没有摘要。\n\n点击“总结当前任务”，整理设计决定、待办事项与经验。";
            var text=new StringBuilder();text.AppendLine(string.IsNullOrWhiteSpace(s.summary)?"暂无任务概述。":s.summary);AppendSection(text,"已经确定",s.decisions);AppendSection(text,"仍需处理",s.open_items);
            var lessons=new List<string>();CollectLessons(s.lessons,lessons);AppendSection(text,"可复用经验",lessons.ToArray());return text.ToString();
        }
        private static void AppendSection(StringBuilder text,string heading,string[] items){if(items==null||items.Length==0)return;text.AppendLine().AppendLine(heading);foreach(string s in items)if(!string.IsNullOrWhiteSpace(s))text.AppendLine("• "+s);}
        private static void CollectLessons(object value,List<string> output)
        {
            var s=value as string;if(s!=null){if(!string.IsNullOrWhiteSpace(s))output.Add(s);return;}
            var d=value as Dictionary<string,object>;if(d!=null){foreach(string key in new[]{"text","lesson","summary","description"})if(d.ContainsKey(key)){CollectLessons(d[key],output);return;}return;}
            var a=value as System.Collections.IEnumerable;if(a!=null)foreach(object item in a)CollectLessons(item,output);
        }
        protected override void Dispose(bool disposing)
        {
            if(disposing&&!disposed){disposed=true;sessionSequence++;skillSequence++;if(timer!=null){timer.Stop();timer.Dispose();}lock(requests){foreach(var r in requests){try{r.Abort();}catch{}}requests.Clear();}}
            base.Dispose(disposing);
        }
    }
    public sealed class KnowledgeSnapshot {public string project_id{get;set;}public KnowledgeSummary summary{get;set;}public KnowledgeNote[] notes{get;set;}public KnowledgeSession[] sessions{get;set;}public KnowledgeSkill[] skills{get;set;}public KnowledgeStats stats{get;set;}public KnowledgeLearning learning{get;set;}}
    public sealed class KnowledgeSummary {public string summary{get;set;}public string[] decisions{get;set;}public string[] open_items{get;set;}public object lessons{get;set;}}
    public sealed class KnowledgeNote {public string id{get;set;}public string text{get;set;}public string scope{get;set;}public string created_at{get;set;}}
    public sealed class KnowledgeSession {public string project_id{get;set;}public string title{get;set;}public string phase{get;set;}public string updated_at{get;set;}}
    public sealed class KnowledgeSkill {public string id{get;set;}public string name{get;set;}public string title{get;set;}public string description{get;set;}public string version{get;set;}public bool enabled{get;set;}public string path{get;set;}public string source_project_id{get;set;}}
    public sealed class KnowledgeStats {public int sessions{get;set;}public int notes{get;set;}public int skills{get;set;}}
    public sealed class KnowledgeLearning {public bool busy{get;set;}public string status{get;set;}public string error{get;set;}}
    public sealed class KnowledgeSessionDetail {public string title{get;set;}public object summary{get;set;}public KnowledgeMessage[] messages{get;set;}public string phase{get;set;}}
    public sealed class KnowledgeMessage {public string role{get;set;}public string content{get;set;}public string at{get;set;}}
    public sealed class KnowledgeSkillDetail {public string content{get;set;}public string path{get;set;}public string name{get;set;}}
}
