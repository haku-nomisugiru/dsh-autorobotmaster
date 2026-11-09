using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace RoboMaster.Workbench
{
    /// <summary>Configure an API provider without exposing persisted secrets.</summary>
    public sealed class ApiSettingsDialog : Form
    {
        private readonly string serviceUrl, token;
        private readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 1024 * 1024 };
        private readonly HashSet<HttpWebRequest> requests = new HashSet<HttpWebRequest>();
        private readonly ComboBox protocol, structured, tokenParameter;
        private readonly TextBox endpoint, model, apiKey, apiKeyEnv;
        private readonly NumericUpDown timeout, maxTokens;
        private readonly CheckBox clearKey;
        private readonly Label keyStatus, status;
        private readonly Button save, test, cancelTest, reload, advancedToggle;
        private readonly TableLayoutPanel fields;
        private readonly GroupBox advanced;
        private readonly int advancedRow;
        private bool disposed, operating, testing, cancelled, loaded;
        private HttpWebRequest testRequest;
        public event EventHandler SettingsSaved;

        public ApiSettingsDialog(string serviceUrl, string token)
        {
            this.serviceUrl = (serviceUrl ?? "").TrimEnd('/');
            this.token = token ?? "";
            Text = "API设置 — RoboMaster API版 v1.0.0";
            Font = new Font("Microsoft YaHei UI", 9f);
            ForeColor = WorkbenchTheme.Ink;
            BackColor = WorkbenchTheme.Surface;
            AutoScaleMode = AutoScaleMode.Dpi;
            ClientSize = new Size(680, 610);
            MinimumSize = new Size(620, 540);
            StartPosition = FormStartPosition.CenterParent;
            ShowInTaskbar = false;

            var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 4, Margin = Padding.Empty };
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 74));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 63));
            Controls.Add(root);
            var header = new Panel { Dock = DockStyle.Fill, BackColor = WorkbenchTheme.Header, Margin = Padding.Empty };
            header.Controls.Add(new PixelIconControl { Light = true, Location = new Point(20, 19), Size = new Size(20, 20) });
            header.Controls.Add(new Label { Text = "API设置", AutoSize = true, Location = new Point(50, 12), Font = new Font(Font.FontFamily, 15f, FontStyle.Bold), ForeColor = Color.White });
            header.Controls.Add(new Label { Text = "配置设计对话与经验整理使用的接口。", AutoSize = true, Location = new Point(21, 45), Font = new Font(Font.FontFamily, 8f), ForeColor = WorkbenchTheme.HeaderMuted });
            root.Controls.Add(header, 0, 0);
            var scroll = new Panel { Dock = DockStyle.Fill, AutoScroll = true, Padding = new Padding(18, 10, 18, 4), Margin = Padding.Empty, BackColor = Color.White };
            fields = new TableLayoutPanel { Dock = DockStyle.Top, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, ColumnCount = 2, RowCount = 0, Margin = Padding.Empty, BackColor = Color.White };
            fields.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 124));
            fields.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            scroll.Controls.Add(fields);
            root.Controls.Add(scroll, 0, 1);

            protocol = Combo("api.protocol", new[] { "Responses  /responses", "Chat Completions  /chat/completions" });
            endpoint = Field("api.base_url");
            model = Field("api.model");
            apiKey = Field("api.key");
            apiKey.UseSystemPasswordChar = true;
            structured = Combo("api.structured_output", new[] { "JSON Schema（推荐）", "JSON Object（兼容模式）" });
            AddRow("接口协议", protocol, 42);
            AddRow("Base URL", endpoint, 42);
            var endpointHint = new Label { Text = "填写基础地址，例如 https://服务地址/v1，不包含具体接口路径。", AutoSize = false, Dock = DockStyle.Fill, ForeColor = WorkbenchTheme.Muted, Font = new Font(Font.FontFamily, 7.7f), Margin = new Padding(124, 0, 0, 0) };
            AddFull(endpointHint, 24);
            AddRow("模型 ID", model, 42);
            AddRow("API Key", apiKey, 42);
            keyStatus = new Label { Text = "正在读取密钥配置状态…", Dock = DockStyle.Fill, ForeColor = WorkbenchTheme.Muted, Font = new Font(Font.FontFamily, 8f), Margin = new Padding(124, 1, 0, 0), AutoEllipsis = true };
            AddFull(keyStatus, 25);
            clearKey = new CheckBox { Text = "保存时清除已保存的 API Key", AutoSize = true, FlatStyle = FlatStyle.Flat, ForeColor = WorkbenchTheme.Ink, BackColor = Color.White, Margin = new Padding(124, 2, 0, 0), Name = "api.clear_key" };
            clearKey.CheckedChanged += delegate { if (clearKey.Checked) apiKey.Clear(); apiKey.Enabled = !operating && !clearKey.Checked; };
            AddFull(clearKey, 28);
            AddRow("结构化输出", structured, 42);
            AddFull(new Label { Text = "兼容模式仍会在本机校验返回结果。API Key 留空会保留现有密钥。", Dock = DockStyle.Fill, ForeColor = WorkbenchTheme.Muted, Font = new Font(Font.FontFamily, 7.7f), Margin = new Padding(124, 0, 0, 0) }, 26);
            advancedToggle = MakeButton("高级选项  ▸", false, 120);
            advancedToggle.Name = "api.advanced"; advancedToggle.TextAlign = ContentAlignment.MiddleLeft;
            AddFull(advancedToggle, 32);
            advanced = new GroupBox { Text = "高级选项", Dock = DockStyle.Fill, BackColor = Color.White, ForeColor = WorkbenchTheme.Ink, Visible = false, Margin = new Padding(0, 3, 0, 2) };
            var advancedFields = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 4, Padding = new Padding(10, 5, 10, 5) };
            advancedFields.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 114));
            advancedFields.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            for (int i = 0; i < 4; i++) advancedFields.RowStyles.Add(new RowStyle(SizeType.Percent, 25));
            timeout = new NumericUpDown { Minimum = 1, Maximum = 600, Value = 120, DecimalPlaces = 0, ThousandsSeparator = false, Name = "api.timeout" };
            maxTokens = new NumericUpDown { Minimum = 32, Maximum = 128000, Value = 4096, DecimalPlaces = 0, ThousandsSeparator = true, Name = "api.max_output_tokens" };
            tokenParameter = Combo("api.token_parameter", new[] { "max_completion_tokens", "max_tokens" });
            apiKeyEnv = Field("api.key_env");
            AddAdvanced(advancedFields, 0, "超时（秒）", timeout);
            AddAdvanced(advancedFields, 1, "最大输出 Token", maxTokens);
            AddAdvanced(advancedFields, 2, "Token 参数", tokenParameter);
            AddAdvanced(advancedFields, 3, "密钥环境变量", apiKeyEnv);
            advanced.Controls.Add(advancedFields);
            advancedRow = fields.RowCount;
            AddFull(advanced, 0);
            advancedToggle.Click += delegate { advanced.Visible = !advanced.Visible; fields.RowStyles[advancedRow].Height = advanced.Visible ? 174 : 0; advancedToggle.Text = advanced.Visible ? "高级选项  ▾" : "高级选项  ▸"; };
            protocol.SelectedIndexChanged += delegate { UpdateControls(); };
            var actions = new Panel { Dock = DockStyle.Fill, Padding = new Padding(18, 7, 18, 7), Margin = Padding.Empty };
            test = MakeButton("测试当前配置", false, 123); test.Name = "api.test"; test.Dock = DockStyle.Left;
            cancelTest = MakeButton("停止等待", false, 88); cancelTest.Name = "api.cancel_test"; cancelTest.Dock = DockStyle.Left; cancelTest.Visible = false;
            reload = MakeButton("重新读取", false, 88); reload.Dock = DockStyle.Left;
            save = MakeButton("保存设置", true, 96); save.Name = "api.save"; save.Dock = DockStyle.Right;
            var close = MakeButton("关闭", false, 66); close.Dock = DockStyle.Right;
            test.Click += async delegate { await TestAsync(); };
            cancelTest.Click += delegate { CancelTest(); };
            reload.Click += async delegate { await LoadSettingsAsync(); };
            save.Click += async delegate { await SaveAsync(); };
            close.Click += delegate { Close(); };
            actions.Controls.Add(reload); actions.Controls.Add(cancelTest); actions.Controls.Add(test); actions.Controls.Add(save); actions.Controls.Add(close);
            root.Controls.Add(actions, 0, 2);
            status = new Label { Dock = DockStyle.Fill, Text = "读取配置不会向模型服务发送请求。", Padding = new Padding(19, 6, 19, 6), ForeColor = WorkbenchTheme.Muted, BackColor = WorkbenchTheme.Surface, Name = "api.status", AutoEllipsis = true };
            root.Controls.Add(status, 0, 3);
            Shown += async delegate { await LoadSettingsAsync(); };
            UpdateControls();
        }

        private TextBox Field(string name) { return new TextBox { Name = name, ForeColor = WorkbenchTheme.Ink, BackColor = Color.White, BorderStyle = BorderStyle.FixedSingle, MaxLength = name == "api.key" ? 8192 : 2048 }; }
        private ComboBox Combo(string name, string[] choices)
        {
            var combo = new ComboBox { Name = name, DropDownStyle = ComboBoxStyle.DropDownList, DrawMode = DrawMode.OwnerDrawFixed, FlatStyle = FlatStyle.Flat, BackColor = Color.White, ForeColor = WorkbenchTheme.Ink };
            combo.Items.AddRange(choices); combo.SelectedIndex = 0;
            combo.DrawItem += delegate(object sender, DrawItemEventArgs e) {
                if (e.Index < 0) return;
                Color background = (e.State & DrawItemState.Selected) != 0 ? WorkbenchTheme.Selection : Color.White;
                using (var brush = new SolidBrush(background)) e.Graphics.FillRectangle(brush, e.Bounds);
                Rectangle bounds = e.Bounds; bounds.Inflate(-4, 0);
                TextRenderer.DrawText(e.Graphics, Convert.ToString(combo.Items[e.Index]), combo.Font, bounds, WorkbenchTheme.Ink, TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix | TextFormatFlags.SingleLine);
            };
            return combo;
        }
        private Button MakeButton(string text, bool primary, int width)
        {
            var button = new Button { Text = text, Width = width, Height = 30, FlatStyle = FlatStyle.Flat, Cursor = Cursors.Hand, BackColor = primary ? WorkbenchTheme.Accent : Color.White, ForeColor = primary ? Color.White : WorkbenchTheme.Ink, UseVisualStyleBackColor = false, Margin = new Padding(0, 0, 7, 0) };
            button.FlatAppearance.BorderSize = primary ? 0 : 1; button.FlatAppearance.BorderColor = WorkbenchTheme.Border;

            button.FlatAppearance.MouseOverBackColor = primary ? WorkbenchTheme.Ink : WorkbenchTheme.Surface;
            button.FlatAppearance.MouseDownBackColor = primary ? WorkbenchTheme.Header : WorkbenchTheme.Selection;
            return button;
        }
        private void AddRow(string label, Control field, int height)
        {
            int row = fields.RowCount++; fields.RowStyles.Add(new RowStyle(SizeType.Absolute, height));
            fields.Controls.Add(new Label { Text = label, Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft, Margin = new Padding(0, 0, 8, 0) }, 0, row);
            field.Dock = DockStyle.Fill; field.Margin = new Padding(0, 8, 0, 7); fields.Controls.Add(field, 1, row);
        }
        private void AddFull(Control control, int height)
        {
            int row = fields.RowCount++; fields.RowStyles.Add(new RowStyle(SizeType.Absolute, height));
            fields.Controls.Add(control, 0, row); fields.SetColumnSpan(control, 2);
        }
        private static void AddAdvanced(TableLayoutPanel table, int row, string label, Control field)
        {
            table.Controls.Add(new Label { Text = label, Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft }, 0, row);
            field.Dock = DockStyle.Fill; field.Margin = new Padding(0, 4, 0, 4); table.Controls.Add(field, 1, row);
        }

        public async Task<bool> LoadSettingsAsync()
        {
            if (disposed || operating) return false;
            SetOperation(false, true);
            try
            {
                var view = json.Deserialize<ApiSettingsView>(await RequestAsync("GET", "/api/settings", null, 6000, false));
                if (disposed) return false;
                if (view == null) throw new InvalidDataException("没有读到 API 配置。");
                protocol.SelectedIndex = view.protocol == "chat_completions" ? 1 : 0;
                endpoint.Text = view.base_url ?? ""; model.Text = view.model ?? "";
                structured.SelectedIndex = view.structured_output == "json_object" ? 1 : 0;
                timeout.Value = Clamp(view.timeout_seconds > 0 ? view.timeout_seconds : 120, timeout.Minimum, timeout.Maximum);
                maxTokens.Value = Clamp(view.max_output_tokens > 0 ? view.max_output_tokens : 4096, maxTokens.Minimum, maxTokens.Maximum);
                tokenParameter.SelectedIndex = view.token_parameter == "max_tokens" ? 1 : 0;
                apiKeyEnv.Text = view.api_key_env ?? "";
                apiKey.Clear(); clearKey.Checked = false;
                keyStatus.Text = view.has_api_key ? "已配置 API Key · 来源：" + SourceLabel(view.key_source, view.api_key_env) : "尚未配置 API Key";
                loaded = true;
                if (!string.IsNullOrWhiteSpace(view.error)) ShowStatus("配置读取存在问题：" + SafeError(view.error, "") + " 可修改后重新保存。", true);
                else ShowStatus(view.has_api_key && !string.IsNullOrWhiteSpace(view.model) ? "设置已读取。保存不会自动测试；测试使用当前输入的草稿。" : "填写基础地址、模型 ID 和密钥后保存，或先测试当前配置。", false);
                return true;
            }
            catch (Exception ex) { if (!disposed) ShowStatus(SafeError(ex.Message, apiKey.Text), true); return false; }
            finally { if (!disposed) SetOperation(false, false); }
        }
        private static decimal Clamp(double value, decimal min, decimal max) { return Math.Max(min, Math.Min(max, (decimal)value)); }
        private Dictionary<string, object> Draft()
        {
            string url = endpoint.Text.Trim(), modelName = model.Text.Trim();
            Uri uri;
            if (!Uri.TryCreate(url, UriKind.Absolute, out uri) || (uri.Scheme != "https" && uri.Scheme != "http")) throw new InvalidOperationException("请填写有效的 HTTP 或 HTTPS 基础地址。");
            if (!string.IsNullOrEmpty(uri.UserInfo)) throw new InvalidOperationException("基础地址不能包含登录凭据，请使用 API Key 输入框。");
            if (string.IsNullOrWhiteSpace(modelName)) throw new InvalidOperationException("请填写模型服务提供的模型 ID。");
            var draft = new Dictionary<string, object> {
                {"protocol", protocol.SelectedIndex == 1 ? "chat_completions" : "responses"},
                {"base_url", url.TrimEnd('/')}, {"model", modelName},
                {"structured_output", structured.SelectedIndex == 1 ? "json_object" : "json_schema"},
                {"timeout_seconds", Decimal.ToInt32(timeout.Value)}, {"max_output_tokens", Decimal.ToInt32(maxTokens.Value)},
                {"api_key_env", apiKeyEnv.Text.Trim()}, {"token_parameter", tokenParameter.SelectedIndex == 1 ? "max_tokens" : "max_completion_tokens"}
            };
            if (clearKey.Checked) draft["clear_api_key"] = true;
            else if (!string.IsNullOrWhiteSpace(apiKey.Text)) draft["api_key"] = apiKey.Text.Trim();
            return draft;
        }
        private async Task SaveAsync()
        {
            if (operating || disposed) return;
            Dictionary<string, object> draft = null; string secret = apiKey.Text; bool success = false;
            try
            {
                draft = Draft(); SetOperation(false, true);
                await RequestAsync("POST", "/api/settings", draft, 6000, false);
                success = !disposed;
            }
            catch (Exception ex) { if (!disposed) ShowStatus(SafeError(ex.Message, secret), true); }
            finally
            {
                if (draft != null) draft.Remove("api_key");
                if (!disposed) { if (success) apiKey.Clear(); SetOperation(false, false); }
            }
            if (success && !disposed)
            {
                bool refreshed = await LoadSettingsAsync();
                if (disposed) return;
                if (refreshed) ShowStatus("设置已保存。下一次设计对话和经验整理将使用这些配置。", false);
                var handler = SettingsSaved; if (handler != null) handler(this, EventArgs.Empty);
            }
        }
        private async Task TestAsync()
        {
            if (operating || disposed) return;
            Dictionary<string, object> draft = null; string secret = apiKey.Text;
            try
            {
                draft = Draft(); SetOperation(true, true);
                ShowStatus("正在测试当前草稿配置… 此操作不会自动保存。", false);
                string response = await RequestAsync("POST", "/api/settings/test", draft, 180000, true);
                if (disposed) return;
                var result = json.Deserialize<ApiTestReply>(response);
                if (result == null) throw new InvalidDataException("连接测试没有返回可读结果。");
                string detail = SafeError(result.message ?? (result.ok ? "接口响应正常。" : "服务未通过测试。"), secret);
                ShowStatus((result.ok ? "测试通过：" : "测试未通过：") + detail + (result.ok ? "\r\n模型：" + SafeError(result.model ?? model.Text, secret) + " · 耗时 " + result.elapsed_ms.ToString("0") + " ms。设置尚未自动保存。" : ""), !result.ok);
            }
            catch (OperationCanceledException) { if (!disposed) ShowStatus("已停止等待测试结果。可修改配置后重新测试。", false); }
            catch (Exception ex) { if (!disposed) ShowStatus(SafeError(ex.Message, secret), true); }
            finally
            {
                if (draft != null) draft.Remove("api_key");
                if (!disposed) SetOperation(false, false);
            }
        }
        private void SetOperation(bool isTest, bool value) { operating = value; testing = value && isTest; if (value) cancelled = false; UpdateControls(); }
        private void UpdateControls()
        {
            if (fields == null) return;
            fields.Enabled = !operating;
            if (apiKey != null) apiKey.Enabled = !operating && (clearKey == null || !clearKey.Checked);
            if (tokenParameter != null) tokenParameter.Enabled = !operating && protocol.SelectedIndex == 1;
            if (save != null) save.Enabled = loaded && !operating;
            if (test != null) test.Enabled = loaded && !operating;
            if (reload != null) reload.Enabled = !operating;
            if (cancelTest != null) { cancelTest.Visible = testing; cancelTest.Enabled = testing && !cancelled; }
        }
        private void CancelTest()
        {
            if (!testing) return; cancelled = true;
            var current = testRequest; if (current != null) { try { current.Abort(); } catch { } }
            UpdateControls();
        }
        private async Task<string> RequestAsync(string method, string path, object payload, int milliseconds, bool isTest)
        {
            var request = (HttpWebRequest)WebRequest.Create(serviceUrl + path);
            request.Method = method; request.Proxy = null; request.Timeout = milliseconds; request.ReadWriteTimeout = milliseconds;
            request.Headers["X-Workbench-Token"] = token;
            lock (requests) requests.Add(request);
            if (isTest) testRequest = request;
            using (var deadline = new CancellationTokenSource())
            using (deadline.Token.Register(delegate { try { request.Abort(); } catch { } }))
            {
                deadline.CancelAfter(milliseconds);
                try
                {
                    if (payload != null)
                    {
                        byte[] bytes = Encoding.UTF8.GetBytes(json.Serialize(payload));
                        request.ContentType = "application/json; charset=utf-8"; request.ContentLength = bytes.Length;
                        using (Stream stream = await request.GetRequestStreamAsync()) await stream.WriteAsync(bytes, 0, bytes.Length);
                    }
                    using (var response = await request.GetResponseAsync())
                    using (var reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8)) return await reader.ReadToEndAsync();
                }
                catch (WebException ex)
                {
                    if (disposed || (isTest && cancelled)) throw new OperationCanceledException();
                    if (deadline.IsCancellationRequested) throw new TimeoutException(isTest ? "连接测试等待超时，请检查服务地址和接口配置。" : "本地设置服务响应超时，请稍后重新读取。");
                    if (ex.Response != null)
                    {
                        using (var response = ex.Response)
                        using (var reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8))
                        {
                            string text = await reader.ReadToEndAsync();
                            Dictionary<string, object> error = null;
                            try { error = json.Deserialize<Dictionary<string, object>>(text); } catch { }
                            if (error != null)
                            {
                                object message;
                                if (error.TryGetValue("error", out message) || error.TryGetValue("message", out message)) throw new InvalidOperationException(Convert.ToString(message));
                            }
                        }
                    }
                    throw new InvalidOperationException("无法连接本地设置服务，请重新读取或运行环境诊断。");
                }
                finally
                {
                    lock (requests) requests.Remove(request);

                    if (object.ReferenceEquals(testRequest, request)) testRequest = null;
                }
            }
        }
        private void ShowStatus(string message, bool error) { status.Text = message; status.ForeColor = error ? WorkbenchTheme.Ink : WorkbenchTheme.Muted; }
        private static string SourceLabel(string source, string environment)
        {
            source = source ?? "";
            string lower = source.ToLowerInvariant();
            if (lower.Contains("env")) return "环境变量" + (string.IsNullOrWhiteSpace(environment) ? "" : " " + environment);
            if (lower.Contains("local") || lower.Contains("saved") || lower.Contains("stored") || lower.Contains("dpapi") || lower.Contains("encrypted")) return "此设备已保存";
            if (string.IsNullOrWhiteSpace(source) || lower == "none") return "已配置";
            foreach (char c in source) if (c > 127) return source;
            return "服务提供的配置";
        }
        private static string SafeError(string message, string knownSecret)
        {
            string text = message ?? "操作未完成。";
            if (!string.IsNullOrWhiteSpace(knownSecret)) text = text.Replace(knownSecret, "[密钥已隐藏]");
            text = Regex.Replace(text, @"\bsk-[A-Za-z0-9_-]{8,}", "[密钥已隐藏]");
            text = Regex.Replace(text, @"(?i)(bearer\s+)\S+", "$1[密钥已隐藏]");
            return text.Length > 700 ? text.Substring(0, 700) : text;
        }
        protected override void Dispose(bool disposing)
        {
            if (disposing && !disposed)
            {
                disposed = true;
                if (apiKey != null) apiKey.Clear();
                lock (requests) { foreach (var request in requests) { try { request.Abort(); } catch { } } requests.Clear(); }
            }
            base.Dispose(disposing);
        }
    }
    public sealed class ApiSettingsView
    {
        public string protocol { get; set; } public string base_url { get; set; } public string model { get; set; }
        public string structured_output { get; set; } public double timeout_seconds { get; set; } public int max_output_tokens { get; set; }
        public string api_key_env { get; set; } public string token_parameter { get; set; }
        public bool has_api_key { get; set; } public string key_source { get; set; } public string error { get; set; }
    }
    public sealed class ApiTestReply
    {
        public bool ok { get; set; } public string message { get; set; } public string model { get; set; }
        public string protocol { get; set; } public double elapsed_ms { get; set; }
    }
}
