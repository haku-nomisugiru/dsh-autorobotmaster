using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Net;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace RoboMaster.Workbench
{
    public sealed class WorkbenchControl : UserControl
    {
        private static readonly Color Ink = WorkbenchTheme.Ink;
        private static readonly Color Muted = WorkbenchTheme.Muted;
        private static readonly Color Surface = WorkbenchTheme.Surface;
        private static readonly Color Accent = WorkbenchTheme.Accent;
        private readonly string baseUrl;
        private readonly string token;
        private readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 4 * 1024 * 1024 };
        private readonly System.Windows.Forms.Timer pollTimer;
        private readonly HashSet<HttpWebRequest> requests = new HashSet<HttpWebRequest>();
        private readonly Label statusPill, projectLabel, documentLabel, progressLabel, planLabel;
        private readonly LinkLabel footnote;
        private readonly FlowLayoutPanel chatFlow, stepsFlow;
        private readonly TextBox input;
        private readonly Button sendButton, runButton, controlButton, cancelButton, newButton, outputsButton, refreshButton, knowledgeButton, apiSettingsButton;
        private KnowledgeDialog knowledgeDialog;
        private ApiSettingsDialog apiSettingsDialog;
        private readonly MonochromeProgressBar progress;
        private readonly SplitContainer split;
        private readonly string layoutPath;
        private double topPanelRatio = 0.5;
        private bool applyingPanelRatio, userMovingSplitter;
        private WorkbenchState state;
        private long lastRevision = long.MinValue;
        private bool polling, commandPending, disposed, preview;

        public WorkbenchControl(string baseUrl, string token)
        {
            this.baseUrl = (baseUrl ?? "").TrimEnd('/');
            this.token = token ?? "";
            layoutPath = Path.Combine(Path.GetFullPath(Path.Combine(Path.GetDirectoryName(typeof(WorkbenchControl).Assembly.Location), "..")), "data", "ui-layout.json");
            ReadPanelRatio();
            Font = new Font("Microsoft YaHei UI", 9f, FontStyle.Regular, GraphicsUnit.Point);
            ForeColor = Ink;
            BackColor = Surface;
            Size = new Size(400, 860);
            AutoScaleMode = AutoScaleMode.Dpi;
            DoubleBuffered = true;

            var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 4, BackColor = Surface, Margin = Padding.Empty, Padding = Padding.Empty };
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 78));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 55));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 58));
            Controls.Add(root);

            var brand = new Panel { Dock = DockStyle.Fill, BackColor = WorkbenchTheme.Header, Margin = Padding.Empty };
            var monogram = new PixelIconControl { Light = true, Location = new Point(16, 17), Size = new Size(20, 20), AccessibleName = "RoboMaster 像素图标" };
            var wordmark = new Label { Text = "ROBOMASTER", Font = new Font("Segoe UI", 10f, FontStyle.Bold), ForeColor = Color.White, AutoSize = true, Location = new Point(44, 17) };
            var brandCaption = new Label { Text = "机械设计工作台  /  API v1.0.0", Font = new Font("Microsoft YaHei UI", 8f), ForeColor = WorkbenchTheme.HeaderMuted, AutoSize = true, Location = new Point(44, 42) };
            statusPill = new Label { Text = "连接中", Font = new Font("Microsoft YaHei UI", 8f), ForeColor = Color.White, BackColor = Color.FromArgb(58, 58, 58), TextAlign = ContentAlignment.MiddleCenter, Size = new Size(74, 25), Anchor = AnchorStyles.Top | AnchorStyles.Right, Location = new Point(309, 25) };
            brand.Resize += delegate { statusPill.Left = Math.Max(219, brand.ClientSize.Width - statusPill.Width - 14); brandCaption.Text = brand.ClientSize.Width < 350 ? "机械设计工作台 · API版" : "机械设计工作台 / API v1.0.0"; };
            brand.Controls.AddRange(new Control[] { monogram, wordmark, brandCaption, statusPill });
            root.Controls.Add(brand, 0, 0);

            var context = new Panel { Dock = DockStyle.Fill, Margin = Padding.Empty, BackColor = Color.White, Padding = new Padding(16, 7, 16, 6) };
            projectLabel = new Label { Text = "新建机械设计", Dock = DockStyle.Top, Height = 21, Font = new Font(Font, FontStyle.Bold), AutoEllipsis = true };
            documentLabel = new Label { Text = "当前文档：等待连接", Dock = DockStyle.Fill, ForeColor = Muted, Font = new Font(Font.FontFamily, 8f), AutoEllipsis = true };
            context.Controls.Add(documentLabel); context.Controls.Add(projectLabel);
            root.Controls.Add(context, 0, 1);

            split = new AdjustableSplitContainer { Dock = DockStyle.Fill, Orientation = Orientation.Horizontal, BackColor = Surface, SplitterWidth = 12, Margin = new Padding(10, 8, 10, 0), FixedPanel = FixedPanel.None, IsSplitterFixed = false, Size = new Size(380, 670), Panel1MinSize = 190, Panel2MinSize = 210, SplitterDistance = 329 };
            split.SplitterMoving += delegate { if (!applyingPanelRatio) userMovingSplitter = true; };
            split.SplitterMoved += delegate
            {
                if (!applyingPanelRatio && userMovingSplitter)
                {
                    int span = split.ClientSize.Height - split.SplitterWidth;
                    if (span > 0) topPanelRatio = (double)split.SplitterDistance / span;
                    userMovingSplitter = false;
                    SavePanelRatio();
                }
            };
            split.SizeChanged += delegate { ApplyPanelRatio(); };
            root.Controls.Add(split, 0, 2);

            var design = new Panel { Dock = DockStyle.Fill, BackColor = Color.White, Padding = new Padding(10, 0, 10, 8) };
            split.Panel2.Controls.Add(design);
            var designTitle = SectionTitle("02", "设计", "讨论需求，形成可执行方案");
            design.Controls.Add(designTitle);
            var composer = new Panel { Dock = DockStyle.Bottom, Height = 102, Padding = new Padding(0, 6, 0, 0), BackColor = Color.White };
            var inputShell = new Panel { Dock = DockStyle.Fill, BackColor = Surface, Padding = new Padding(9, 7, 9, 7) };
            input = new TextBox { Dock = DockStyle.Fill, Multiline = true, AcceptsReturn = true, ScrollBars = ScrollBars.Vertical, BorderStyle = BorderStyle.None, BackColor = Surface, ForeColor = Ink, Font = Font, MaxLength = 8000 };
            input.KeyDown += async delegate(object sender, KeyEventArgs e) { if (e.Control && e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; await SendAsync(); } };
            inputShell.Controls.Add(input);
            var composerFooter = new Panel { Dock = DockStyle.Bottom, Height = 34, Padding = new Padding(0, 4, 0, 0) };
            var keyboardHint = new Label { Text = "描述零件、尺寸与修改要求", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft, ForeColor = Muted, Font = new Font(Font.FontFamily, 7.8f) };
            sendButton = MakeButton("发送  ↗", true); sendButton.Dock = DockStyle.Right; sendButton.Width = 84;
            sendButton.Click += async delegate { await SendAsync(); };
            composerFooter.Controls.Add(keyboardHint); composerFooter.Controls.Add(sendButton);
            composer.Controls.Add(inputShell); composer.Controls.Add(composerFooter);
            design.Controls.Add(composer);
            planLabel = new Label { Dock = DockStyle.Bottom, Height = 0, Padding = new Padding(8), BackColor = Color.FromArgb(238, 238, 238), ForeColor = Accent, Font = new Font(Font.FontFamily, 8f), AutoEllipsis = true, Visible = false };
            design.Controls.Add(planLabel);
            chatFlow = MakeFlow();
            chatFlow.Resize += delegate { ResizeCards(chatFlow); };
            design.Controls.Add(chatFlow); design.Controls.SetChildIndex(chatFlow, 0); design.Controls.SetChildIndex(planLabel, 1); design.Controls.SetChildIndex(composer, 2); design.Controls.SetChildIndex(designTitle, 3);

            var execution = new Panel { Dock = DockStyle.Fill, BackColor = Color.White, Padding = new Padding(10, 0, 10, 8) };
            split.Panel1.Controls.Add(execution);
            var executionTitle = SectionTitle("01", "建模与验收", "每一步都有结果，每一轮都可追踪");
            execution.Controls.Add(executionTitle);
            var executionFooter = new Panel { Dock = DockStyle.Bottom, Height = 75, BackColor = Color.White };
            var buttonRow = new TableLayoutPanel { Dock = DockStyle.Bottom, Height = 31, ColumnCount = 2, RowCount = 1, Padding = Padding.Empty, Margin = Padding.Empty };
            buttonRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50)); buttonRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
            controlButton = MakeButton("暂停", false); controlButton.Dock = DockStyle.Fill; controlButton.Margin = new Padding(0, 0, 4, 0);
            cancelButton = MakeButton("取消任务", false); cancelButton.Dock = DockStyle.Fill; cancelButton.Margin = new Padding(4, 0, 0, 0);
            controlButton.Click += async delegate { if (state == null) return; await CommandAsync("/api/control", new { action = state.phase == "paused" ? "resume" : (state.phase == "failed" || state.phase == "review_required" || state.phase == "cancelled") ? "retry" : "pause" }); };
            cancelButton.Click += async delegate { await CommandAsync("/api/control", new { action = "cancel" }); };
            buttonRow.Controls.Add(controlButton, 0, 0); buttonRow.Controls.Add(cancelButton, 1, 0);
            runButton = MakeButton("开始建模", true); runButton.Dock = DockStyle.Top; runButton.Height = 35;
            runButton.Click += async delegate { if (state != null && state.phase == "review_required") await CommandAsync("/api/control", new { action = "accept" }); else await CommandAsync("/api/run", new { }); };
            executionFooter.Controls.Add(buttonRow); executionFooter.Controls.Add(runButton); execution.Controls.Add(executionFooter);
            var progressPanel = new Panel { Dock = DockStyle.Top, Height = 41, Padding = new Padding(2, 0, 2, 6) };
            progressLabel = new Label { Text = "等待设计方案", Dock = DockStyle.Top, Height = 24, ForeColor = Muted, Font = new Font(Font.FontFamily, 8f) };
            progress = new MonochromeProgressBar { Dock = DockStyle.Bottom, Height = 5, Minimum = 0, Maximum = 100, Value = 0, Style = ProgressBarStyle.Continuous };
            progressPanel.Controls.Add(progressLabel); progressPanel.Controls.Add(progress);
            execution.Controls.Add(progressPanel);
            stepsFlow = MakeFlow(); stepsFlow.Resize += delegate { ResizeCards(stepsFlow); };
            execution.Controls.Add(stepsFlow); execution.Controls.SetChildIndex(stepsFlow, 0); execution.Controls.SetChildIndex(executionFooter, 1); execution.Controls.SetChildIndex(progressPanel, 2); execution.Controls.SetChildIndex(executionTitle, 3);

            var footer = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2, ColumnCount = 6, Padding = new Padding(10, 3, 10, 1), Margin = Padding.Empty };
            foreach (float width in new float[] { 19, 23, 19, 12, 12, 15 }) footer.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, width));
            footer.RowStyles.Add(new RowStyle(SizeType.Absolute, 28)); footer.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            apiSettingsButton = MakeButton("API设置", true); apiSettingsButton.Dock = DockStyle.Fill; apiSettingsButton.Name = "workbench.api_settings"; apiSettingsButton.Font = new Font(Font.FontFamily, 8f); apiSettingsButton.Margin = new Padding(0, 0, 3, 0); apiSettingsButton.Click += delegate { OpenApiSettings(); };
            knowledgeButton = LinkButton("记忆与 Skill"); knowledgeButton.Name = "workbench.knowledge"; knowledgeButton.Click += delegate { OpenKnowledge(); };
            outputsButton = LinkButton("产物目录"); outputsButton.Name = "workbench.outputs"; outputsButton.Click += delegate { OpenOutputs(); };
            newButton = LinkButton("新建"); newButton.Name = "workbench.new"; newButton.Click += async delegate { await CommandAsync("/api/new", new { }); };
            refreshButton = LinkButton("刷新"); refreshButton.Name = "workbench.refresh"; refreshButton.Click += async delegate { await RefreshStateAsync(); };
            footer.Controls.Add(apiSettingsButton, 0, 0); footer.Controls.Add(knowledgeButton, 1, 0); footer.Controls.Add(outputsButton, 2, 0); footer.Controls.Add(newButton, 3, 0); footer.Controls.Add(refreshButton, 4, 0);
            var libraryButton = LinkButton("模型库"); libraryButton.Name = "workbench.library";
            libraryButton.Click += delegate { if (disposed || preview || string.IsNullOrWhiteSpace(baseUrl)) return; using (var dialog = new CadLibraryDialog(RequestAsync)) dialog.ShowDialog(FindForm()); };
            footer.Controls.Add(libraryButton, 5, 0);
            footnote = new LinkLabel { Text = "正在读取 API 配置状态…", LinkColor = Muted, ActiveLinkColor = Ink, VisitedLinkColor = Muted, LinkBehavior = LinkBehavior.HoverUnderline, Font = new Font(Font.FontFamily, 7.5f), Dock = DockStyle.Fill, AutoEllipsis = true, Name = "workbench.api_status" };
            footnote.LinkClicked += delegate { OpenApiSettings(); };
            footer.Controls.Add(footnote, 0, 1); footer.SetColumnSpan(footnote, 6);
            root.Controls.Add(footer, 0, 3);
            ApplyPanelRatio();
            SetEmptyState();
            UpdateButtons();
            pollTimer = new System.Windows.Forms.Timer { Interval = 1000 };
            pollTimer.Tick += async delegate { await RefreshStateAsync(); };
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            ApplyPanelRatio();
            if (!preview && !disposed) { pollTimer.Start(); BeginInvoke((Action)(async delegate { await RefreshStateAsync(); })); }
        }

        private void ReadPanelRatio()
        {
            try
            {
                if (!File.Exists(layoutPath)) return;
                var saved = json.Deserialize<Dictionary<string, object>>(File.ReadAllText(layoutPath, Encoding.UTF8));
                object value;
                if (saved != null && saved.TryGetValue("top_panel_ratio", out value))
                {
                    double ratio = Convert.ToDouble(value, System.Globalization.CultureInfo.InvariantCulture);
                    if (!double.IsNaN(ratio) && !double.IsInfinity(ratio) && ratio > 0 && ratio < 1) topPanelRatio = ratio;
                }
            }
            catch { /* A missing or damaged preference falls back to an equal split. */ }
        }

        private void SavePanelRatio()
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(layoutPath));
                File.WriteAllText(layoutPath, json.Serialize(new { top_panel_ratio = topPanelRatio }), Encoding.UTF8);
            }
            catch { /* Layout persistence must not interrupt the running CAD task. */ }
        }

        private void ApplyPanelRatio()
        {
            if (split == null || applyingPanelRatio) return;
            int span = split.ClientSize.Height - split.SplitterWidth;
            if (span < split.Panel1MinSize + split.Panel2MinSize) return;
            applyingPanelRatio = true;
            try
            {
                int distance = Math.Max(split.Panel1MinSize, Math.Min(span - split.Panel2MinSize, (int)Math.Round(span * topPanelRatio)));
                if (split.SplitterDistance != distance) split.SplitterDistance = distance;
            }
            finally { applyingPanelRatio = false; }
        }

        private Panel SectionTitle(string number, string title, string subtitle)
        {
            var panel = new Panel { Dock = DockStyle.Top, Height = 47, BackColor = Color.White };
            var marker = new Label { Text = number, ForeColor = Accent, Font = new Font("Segoe UI", 8f, FontStyle.Bold), Location = new Point(0, 12), Size = new Size(25, 22), TextAlign = ContentAlignment.MiddleLeft };
            var heading = new Label { Text = title, ForeColor = Ink, Font = new Font(Font.FontFamily, 10f, FontStyle.Bold), Location = new Point(27, 8), AutoSize = true };
            var hint = new Label { Text = subtitle, ForeColor = Muted, Font = new Font(Font.FontFamily, 7.5f), Location = new Point(28, 28), AutoSize = true };
            panel.Controls.AddRange(new Control[] { marker, heading, hint });
            return panel;
        }

        private static FlowLayoutPanel MakeFlow()
        {
            return new FlowLayoutPanel { Dock = DockStyle.Fill, AutoScroll = true, FlowDirection = FlowDirection.TopDown, WrapContents = false, BackColor = Color.White, Margin = Padding.Empty, Padding = new Padding(0, 3, 0, 3) };
        }

        private Button MakeButton(string text, bool primary)
        {
            var button = new Button { Text = text, FlatStyle = FlatStyle.Flat, Cursor = Cursors.Hand, Height = 30, Font = new Font(Font.FontFamily, 8.5f), BackColor = primary ? Accent : Color.White, ForeColor = primary ? Color.White : Ink, UseVisualStyleBackColor = false, Margin = Padding.Empty };
            button.FlatAppearance.BorderSize = primary ? 0 : 1;
            button.FlatAppearance.BorderColor = WorkbenchTheme.Border;
            button.FlatAppearance.MouseOverBackColor = primary ? Color.FromArgb(66, 66, 66) : Surface;
            button.FlatAppearance.MouseDownBackColor = primary ? Color.FromArgb(20, 20, 20) : WorkbenchTheme.Selection;
            button.EnabledChanged += delegate {
                button.BackColor = primary ? (button.Enabled ? Accent : WorkbenchTheme.Selection) : Color.White;
                button.ForeColor = button.Enabled ? (primary ? Color.White : Ink) : Muted;
            };
            return button;
        }

        private Button LinkButton(string text)
        {
            var button = MakeButton(text, false); button.Dock = DockStyle.Fill; button.FlatAppearance.BorderSize = 0; button.ForeColor = Accent; button.Font = new Font(Font.FontFamily, 7.5f); return button;
        }

        private void SetEmptyState()
        {
            ReplaceCards(chatFlow, new Control[] { new TextCard("设计助手", "从一个零件或子装配体开始。\n描述你要做什么，以及已经确定的尺寸。", WorkbenchTheme.Surface, Ink, false) }, false);
            ReplaceCards(stepsFlow, new Control[] { new TextCard("尚未生成步骤", "讨论需求后，执行步骤和验收结果会显示在这里。", Color.FromArgb(249, 249, 249), Muted, false) }, false);
        }

        public async Task RefreshStateAsync()
        {
            if (disposed || preview || polling || string.IsNullOrEmpty(baseUrl)) return;
            polling = true;
            try
            {
                string body = await RequestAsync("GET", "/api/state", null);
                if (disposed) return;
                var next = json.Deserialize<WorkbenchState>(body);
                if (next == null) throw new InvalidDataException("服务没有返回项目状态。");
                ApplyState(next);
            }
            catch (Exception ex)
            {
                if (!disposed)
                {
                    statusPill.Text = "未连接"; statusPill.ForeColor = Color.White;
                    footnote.Text = "连接中断，将自动重连：" + FriendlyError(ex);
                    sendButton.Enabled = runButton.Enabled = controlButton.Enabled = cancelButton.Enabled = newButton.Enabled = false;
                }
            }
            finally { polling = false; }
        }

        private async Task<string> RequestAsync(string method, string path, object payload)
        {
            var request = (HttpWebRequest)WebRequest.Create(baseUrl + path);
            request.Method = method;
            request.Proxy = null;
            int timeout = path == "/api/library/download" ? 600000 : path.StartsWith("/api/library/") ? 15000 : 6000;
            request.Timeout = timeout;
            request.ReadWriteTimeout = timeout;
            request.Headers["X-Workbench-Token"] = token;
            request.KeepAlive = true;
            lock (requests) requests.Add(request);
            try
            {
                if (payload != null)
                {
                    byte[] bytes = Encoding.UTF8.GetBytes(json.Serialize(payload));
                    request.ContentType = "application/json; charset=utf-8";
                    request.ContentLength = bytes.Length;
                    using (Stream stream = await request.GetRequestStreamAsync()) { await stream.WriteAsync(bytes, 0, bytes.Length); }
                }
                Task<WebResponse> responseTask = request.GetResponseAsync();
                if (await Task.WhenAny(responseTask, Task.Delay(timeout)) != responseTask)
                {
                    request.Abort();
                    try { await responseTask; } catch { }
                    throw new TimeoutException("本地服务响应超时，请稍后刷新。");
                }
                using (var response = (HttpWebResponse)await responseTask)
                using (var reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8)) { return await reader.ReadToEndAsync(); }
            }
            catch (WebException ex)
            {
                if (ex.Response != null)
                {
                    using (var response = ex.Response)
                    using (var reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8))
                    {
                        string body = await reader.ReadToEndAsync();
                        try { var error = json.Deserialize<Dictionary<string, object>>(body); if (error != null && error.ContainsKey("error")) throw new InvalidOperationException(Convert.ToString(error["error"])); } catch (InvalidOperationException) { throw; } catch { }
                    }
                }
                throw;
            }
            finally { lock (requests) requests.Remove(request); }
        }

        private async Task SendAsync()
        {
            string message = input.Text.Trim();
            if (message.Length == 0 || commandPending || preview || state == null || state.busy) return;
            bool sent = await CommandAsync("/api/chat", new { message = message });
            if (sent && !disposed) input.Clear();
        }

        private async Task<bool> CommandAsync(string path, object payload)
        {
            if (disposed || preview || commandPending) return false;
            commandPending = true; UpdateButtons();
            try
            {
                await RequestAsync("POST", path, payload);
                if (!disposed) { await RefreshStateAsync(); }
                return true;
            }
            catch (Exception ex)
            {
                if (!disposed) { footnote.Text = FriendlyError(ex); statusPill.Text = "操作未完成"; }
                return false;
            }
            finally { commandPending = false; if (!disposed) UpdateButtons(); }
        }

        private void ApplyState(WorkbenchState next)
        {
            state = next;
            statusPill.Text = PhaseLabel(next.phase);
            statusPill.ForeColor = next.phase == "failed" ? Color.White : WorkbenchTheme.HeaderMuted;
            projectLabel.Text = next.project != null && !string.IsNullOrWhiteSpace(next.project.name) ? next.project.name : "新建机械设计";
            documentLabel.Text = "当前文档：" + (string.IsNullOrWhiteSpace(next.active_document) ? "未打开文档" : next.active_document);
            int total = next.progress == null ? 0 : Math.Max(0, next.progress.total);
            int passed = next.progress == null ? 0 : Math.Max(0, next.progress.passed);
            progress.Value = total == 0 ? 0 : Math.Max(0, Math.Min(100, passed * 100 / total));
            progressLabel.Text = total == 0 ? "等待设计方案" : string.Format("{0} / {1} 步已验收   ·   {2}", passed, total, PhaseLabel(next.phase));
            planLabel.Visible = !string.IsNullOrWhiteSpace(next.plan_summary) || next.phase == "failed";
            planLabel.Height = planLabel.Visible ? 45 : 0;
            planLabel.Text = next.phase == "failed" ? "可返回设计区修改方案，或重试失败步骤。" : next.plan_summary ?? "";
            string ai = next.service == null ? "等待检查" : next.service.ai;
            bool needsConfiguration = !string.IsNullOrWhiteSpace(ai) && (ai.Contains("未配置") || ai.Contains("缺少") || ai.IndexOf("not configured", StringComparison.OrdinalIgnoreCase) >= 0);
            footnote.Text = string.IsNullOrWhiteSpace(next.error) ? (needsConfiguration ? "API 未配置，点击这里设置。" : "API：" + (ai ?? "等待检查") + "  ·  " + PhaseLabel(next.phase)) : next.error;
            if (lastRevision != next.revision)
            {
                lastRevision = next.revision;
                var bubbles = new List<Control>();
                if (next.messages != null) foreach (var m in next.messages)
                {
                    bool mine = m.role == "user";
                    bubbles.Add(new TextCard(mine ? "你" : m.role == "system" ? "项目记录" : "设计助手", m.content ?? "", mine ? Color.FromArgb(235, 235, 235) : WorkbenchTheme.Surface, Ink, mine));
                }
                if (bubbles.Count == 0) bubbles.Add(new TextCard("设计助手", "从一个零件或子装配体开始。\n描述用途、尺寸和希望保留的结构。", Surface, Ink, false));
                ReplaceCards(chatFlow, bubbles.ToArray(), true);
                var cards = new List<Control>();
                if (next.steps != null) for (int i = 0; i < next.steps.Length; i++)
                {
                    var step = next.steps[i];
                    string status = StepLabel(step.status);
                    string attempt = step.attempt > 0 ? "  ·  第 " + step.attempt + " 次尝试" : "";
                    cards.Add(new TextCard((i + 1).ToString("00") + "   " + step.title, status + attempt + (string.IsNullOrWhiteSpace(step.detail) ? "" : "\n" + step.detail), step.status == "passed" ? Color.FromArgb(238, 238, 238) : step.status == "failed" ? Color.FromArgb(225, 225, 225) : step.status == "running" ? Color.FromArgb(242, 242, 242) : Color.FromArgb(249, 249, 249), step.status == "passed" ? Accent : Ink, false));
                }
                if (cards.Count == 0) cards.Add(new TextCard("尚未生成步骤", "讨论需求后，执行步骤和验收结果会显示在这里。", Color.FromArgb(249, 249, 249), Muted, false));
                ReplaceCards(stepsFlow, cards.ToArray(), false);
            }
            UpdateButtons();
        }

        private void UpdateButtons()
        {
            bool ready = state != null && !preview && !disposed && !commandPending;
            string phase = state == null ? "idle" : state.phase;
            bool busy = state != null && state.busy;
            sendButton.Enabled = ready && !busy;
            input.Enabled = ready && !busy;
            newButton.Enabled = ready && !busy;
            runButton.Enabled = ready && !busy && state.steps != null && state.steps.Length > 0 && (phase == "ready" || phase == "idle" || phase == "review_required");
            runButton.Text = phase == "running" ? "正在建模与检查…" : phase == "completed" ? "本轮验收已完成" : phase == "review_required" ? "验收通过" : "开始建模";
            controlButton.Text = phase == "paused" ? "继续" : (phase == "failed" || phase == "review_required" || phase == "cancelled") ? "重试未完成步骤" : "暂停";
            controlButton.Enabled = ready && (phase == "running" || phase == "paused" || phase == "failed" || phase == "review_required" || phase == "cancelled") && state.steps != null && state.steps.Length > 0;
            cancelButton.Enabled = ready && (busy || phase == "paused");
            outputsButton.Enabled = state != null && !string.IsNullOrWhiteSpace(state.output_dir) && !preview;
            refreshButton.Enabled = !commandPending && !preview;
            knowledgeButton.Enabled = !disposed && !preview && !string.IsNullOrWhiteSpace(baseUrl);
            apiSettingsButton.Enabled = !disposed && !preview && !string.IsNullOrWhiteSpace(baseUrl);
            footnote.Enabled = !disposed && !preview && !string.IsNullOrWhiteSpace(baseUrl);
        }

        private static void ResizeCards(FlowLayoutPanel flow)
        {
            int width = Math.Max(120, flow.ClientSize.Width - SystemInformation.VerticalScrollBarWidth - 2);
            foreach (Control card in flow.Controls) card.Width = width;
        }

        private static void ReplaceCards(FlowLayoutPanel flow, Control[] cards, bool followBottom)
        {
            int oldY = -flow.AutoScrollPosition.Y;
            bool atBottom = oldY + flow.ClientSize.Height >= flow.DisplayRectangle.Height - 35;
            flow.SuspendLayout();
            while (flow.Controls.Count > 0) { Control c = flow.Controls[0]; flow.Controls.RemoveAt(0); c.Dispose(); }
            flow.Controls.AddRange(cards);
            ResizeCards(flow);
            flow.ResumeLayout(true);
            if (followBottom && atBottom && flow.Controls.Count > 0) flow.ScrollControlIntoView(flow.Controls[flow.Controls.Count - 1]);
            else flow.AutoScrollPosition = new Point(0, oldY);
        }

        private void OpenApiSettings()
        {
            if (disposed || preview) return;
            if (apiSettingsDialog != null && !apiSettingsDialog.IsDisposed)
            {
                if (apiSettingsDialog.WindowState == FormWindowState.Minimized) apiSettingsDialog.WindowState = FormWindowState.Normal;
                apiSettingsDialog.BringToFront(); apiSettingsDialog.Activate(); return;
            }
            apiSettingsDialog = new ApiSettingsDialog(baseUrl, token);
            apiSettingsDialog.SettingsSaved += async delegate { await RefreshStateAsync(); };
            apiSettingsDialog.FormClosed += delegate { apiSettingsDialog = null; };
            Form owner = FindForm();
            if (owner != null) apiSettingsDialog.Show(owner); else apiSettingsDialog.Show();
        }

        private void OpenKnowledge()
        {
            if (disposed || preview) return;
            if (knowledgeDialog != null && !knowledgeDialog.IsDisposed)
            {
                if (knowledgeDialog.WindowState == FormWindowState.Minimized) knowledgeDialog.WindowState = FormWindowState.Normal;
                knowledgeDialog.BringToFront(); knowledgeDialog.Activate(); return;
            }
            knowledgeDialog = new KnowledgeDialog(baseUrl, token);
            knowledgeDialog.FormClosed += delegate { knowledgeDialog = null; };
            Form owner = FindForm();
            if (owner != null) knowledgeDialog.Show(owner); else knowledgeDialog.Show();
        }

        private void OpenOutputs()
        {
            try
            {
                if (state == null || string.IsNullOrWhiteSpace(state.output_dir) || !Directory.Exists(state.output_dir)) { footnote.Text = "本轮还没有产物目录。"; return; }
                Process.Start(new ProcessStartInfo("explorer.exe", "\"" + state.output_dir + "\"") { UseShellExecute = true });
            }
            catch (Exception ex) { footnote.Text = "无法打开目录：" + FriendlyError(ex); }
        }

        private static string FriendlyError(Exception ex)
        {
            var web = ex as WebException;
            if (web != null && (web.Status == WebExceptionStatus.ConnectFailure || web.Status == WebExceptionStatus.Timeout)) return "本地服务暂时不可用，请稍后刷新。";
            string message = ex.Message ?? "请求未完成。";
            return message.Length > 220 ? message.Substring(0, 220) : message;
        }

        private static string PhaseLabel(string phase)
        {
            switch (phase)
            {
                case "designing": return "正在设计";
                case "ready": return "方案已就绪";
                case "running": return "正在建模";
                case "paused": return "已暂停";
                case "failed": return "需要修复";
                case "review_required": return "待人工验收";
                case "completed": return "验收完成";
                case "cancelled": return "已取消";
                default: return "准备就绪";
            }
        }

        private static string StepLabel(string value)
        {
            switch (value)
            {
                case "passed": return "✓ 已验收";
                case "running": return "正在执行与检查";
                case "failed": return "未通过";
                case "review_required": return "待人工验收";
                case "cancelled": return "已取消";
                default: return "等待执行";
            }
        }

        public void LoadPreviewState()
        {
            preview = true; pollTimer.Stop();
            ApplyState(new WorkbenchState {
                revision = 1, phase = "paused", busy = false,
                project = new WorkbenchProject { name = "云台安装支架 · 界面预览" },
                active_document = "界面预览，未连接 SolidWorks",
                messages = new[] {
                    new WorkbenchMessage { role = "assistant", content = "先确定安装接口、外形尺寸与材料，再生成可编辑的模型。你可以在这里继续讨论和修改需求。" },
                    new WorkbenchMessage { role = "user", content = "制作一块 120 × 80 × 8 mm 安装板，四角开通孔。" },
                    new WorkbenchMessage { role = "assistant", content = "将分为建立主体、加工孔位、保存与检查三个步骤。孔径和边距需要在执行前确定。" }
                },
                steps = new[] {
                    new WorkbenchStep { id = "1", title = "建立参数化主体", status = "pending", attempt = 0, detail = "安装板外形与厚度" },
                    new WorkbenchStep { id = "2", title = "创建安装孔", status = "pending", attempt = 0, detail = "待确定孔径和孔中心距边缘距离" },
                    new WorkbenchStep { id = "3", title = "保存与验收", status = "pending", attempt = 0, detail = "检查模型实体、尺寸与保存结果" }
                },
                plan_summary = "示意方案 · 请先补齐关键尺寸",
                progress = new WorkbenchProgress { total = 3, passed = 0 },
                service = new WorkbenchService { ai = "界面预览", mcp = "未连接" }
            });
            statusPill.Text = "界面预览";
            footnote.Text = "界面预览 · 未连接 · 示例数据不会用于执行";
            UpdateButtons();
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing && !disposed)
            {
                disposed = true;
                if (knowledgeDialog != null && !knowledgeDialog.IsDisposed) knowledgeDialog.Close();
                if (apiSettingsDialog != null && !apiSettingsDialog.IsDisposed) apiSettingsDialog.Close();
                if (pollTimer != null) { pollTimer.Stop(); pollTimer.Dispose(); }
                lock (requests) { foreach (var request in requests) { try { request.Abort(); } catch { } } requests.Clear(); }
            }
            base.Dispose(disposing);
        }

        private sealed class TextCard : Panel
        {
            private readonly Label heading, body;
            internal TextCard(string title, string content, Color background, Color foreground, bool mine)
            {
                BackColor = background; ForeColor = foreground; Margin = new Padding(mine ? 10 : 0, 0, 0, 8); Padding = new Padding(10); Width = 330;
                heading = new Label { Text = title ?? "", ForeColor = mine ? Accent : Muted, BackColor = Color.Transparent, Font = new Font("Microsoft YaHei UI", 7.7f, FontStyle.Bold), AutoSize = false };
                body = new Label { Text = content ?? "", ForeColor = foreground, BackColor = Color.Transparent, Font = new Font("Microsoft YaHei UI", 8.6f), AutoSize = false };
                Controls.Add(heading); Controls.Add(body);
                Resize += delegate { Arrange(); };
                Arrange();
            }
            private void Arrange()
            {
                int width = Math.Max(80, ClientSize.Width - 20);
                int headingHeight = Math.Max(20, TextRenderer.MeasureText(heading.Text, heading.Font, new Size(width, int.MaxValue), TextFormatFlags.WordBreak | TextFormatFlags.NoPadding).Height + 3);
                int bodyHeight = Math.Max(18, TextRenderer.MeasureText(body.Text, body.Font, new Size(width, int.MaxValue), TextFormatFlags.WordBreak | TextFormatFlags.TextBoxControl | TextFormatFlags.NoPadding).Height + 4);
                heading.SetBounds(10, 8, width, headingHeight); body.SetBounds(10, 8 + headingHeight, width, bodyHeight);
                int desired = 18 + headingHeight + bodyHeight;
                if (Height != desired) Height = desired;
            }
        }
    }

    internal sealed class AdjustableSplitContainer : SplitContainer
    {
        private readonly ToolTip hint = new ToolTip();

        public AdjustableSplitContainer()
        {
            SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);
            hint.SetToolTip(this, "上下拖动，调整两个窗口的占比");
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            Rectangle bar = SplitterRectangle;
            using (var background = new SolidBrush(WorkbenchTheme.Selection)) e.Graphics.FillRectangle(background, bar);
            int centerX = bar.Left + bar.Width / 2;
            int centerY = bar.Top + bar.Height / 2;
            using (var pen = new Pen(Color.FromArgb(145, 145, 145), 1))
            {
                e.Graphics.DrawLine(pen, centerX - 20, centerY - 2, centerX + 20, centerY - 2);
                e.Graphics.DrawLine(pen, centerX - 20, centerY + 2, centerX + 20, centerY + 2);
            }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) hint.Dispose();
            base.Dispose(disposing);
        }
    }

    public sealed class WorkbenchState
    {
        public long revision { get; set; }
        public string phase { get; set; }
        public bool busy { get; set; }
        public WorkbenchProject project { get; set; }
        public string active_document { get; set; }
        public WorkbenchMessage[] messages { get; set; }
        public WorkbenchStep[] steps { get; set; }
        public string plan_summary { get; set; }
        public WorkbenchProgress progress { get; set; }
        public string output_dir { get; set; }
        public WorkbenchService service { get; set; }
        public string error { get; set; }
    }
    public sealed class WorkbenchProject { public string name { get; set; } }
    public sealed class WorkbenchMessage { public string role { get; set; } public string content { get; set; } public string at { get; set; } }
    public sealed class WorkbenchStep { public string id { get; set; } public string title { get; set; } public string status { get; set; } public int attempt { get; set; } public string detail { get; set; } }
    public sealed class WorkbenchProgress { public int passed { get; set; } public int total { get; set; } }
    public sealed class WorkbenchService { public string mcp { get; set; } public string ai { get; set; } }
}
