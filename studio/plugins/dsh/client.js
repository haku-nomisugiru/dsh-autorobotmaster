window.__ModuleLoader__.load({
  id: "@robomaster/studio-dsh",
  factory(require) {
    const React = require("react"),
      h = React.createElement;
    const stages = ["requirements", "reuse", "prototype", "modeling", "mates"];
    const sections = [
      "requirements",
      "verifiedParts",
      "assumptions",
      "relations",
      "acceptance",
    ];
    const zh = {
      title: "RoboMaster Studio",
      requirements: "确认组件需求",
      reuse: "可复用组件",
      prototype: "一次性原型机",
      modeling: "建模与验收",
      mates: "添加机械配合",
      verifiedParts: "已核实零件",
      assumptions: "暂定参数",
      relations: "参数关系",
      acceptance: "验收条件",
      settings: "设置",
      refresh: "刷新",
      close: "关闭",
      add: "添加",
      workspace: "模型工作区",
      save: "保存",
      source: "来源 / 证据",
      spec: "结构化规格",
      send: "发送",
      start: "开始",
      prompt: "当前阶段提示词",
      search: "搜索",
      local: "本地 CAD RAG",
      step: "step.parts",
      query: "搜索组件",
      memory: "记忆与技能",
      summarize: "总结本会话",
      import: "导入技能",
      skillName: "技能名称",
      skillBody: "技能内容（Markdown）",
      enable: "启用",
      disable: "停用",
      draft: "草稿",
      wait: "处理中…",
      input: "描述当前步骤…",
      saved: "已保存",
      sent: "已发送到当前会话",
      mcp: "测试 MCP",
      iterations: "建模迭代",
      noIterations: "等待建模记录",
      empty: "暂无记录",
      choose: "等待你的选择",
      collapse: "收起",
      expand: "展开",
      error: "操作失败",
      mcpPython: "MCP Python 路径",
      mcpServer: "MCP server.py 路径",
      rag: "CAD RAG 地址",
      summaryPrompt:
        "请总结当前 RoboMaster 设计会话，调用 robomaster_studio 的 summary 保存摘要。将有真实执行证据的可复用经验用 skill_save 保存为草稿，未验证项必须写明。",
      newSpec: "新增规格",
      file: "读取 Markdown 文件",
      text: "内容",
    };
    const en = {
      title: "RoboMaster Studio",
      requirements: "Requirements",
      reuse: "Reuse",
      prototype: "Prototype",
      modeling: "Model & verify",
      mates: "Mechanical mates",
      verifiedParts: "Verified parts",
      assumptions: "Assumptions",
      relations: "Relations",
      acceptance: "Acceptance",
      settings: "Settings",
      refresh: "Refresh",
      close: "Close",
      add: "Add",
      workspace: "Model workspace",
      save: "Save",
      source: "Source / evidence",
      spec: "Specification",
      send: "Send",
      start: "Start",
      prompt: "Stage prompt",
      search: "Search",
      local: "Local CAD RAG",
      step: "step.parts",
      query: "Search components",
      memory: "Memory & skills",
      summarize: "Summarize session",
      import: "Import skill",
      skillName: "Skill name",
      skillBody: "Skill Markdown",
      enable: "Enable",
      disable: "Disable",
      draft: "Draft",
      wait: "Working…",
      input: "Describe this step…",
      saved: "Saved",
      sent: "Sent to the current conversation",
      mcp: "Test MCP",
      iterations: "Iterations",
      noIterations: "Waiting for iteration records",
      empty: "No records",
      choose: "Your choice is needed",
      collapse: "Collapse",
      expand: "Expand",
      error: "Action failed",
      mcpPython: "MCP Python path",
      mcpServer: "MCP server.py path",
      rag: "CAD RAG URL",
      summaryPrompt:
        "Summarize this RoboMaster conversation with the summary action. Save reusable experience supported by actual tool evidence using skill_save. Label unverified assumptions explicitly.",
      newSpec: "Add specification",
      file: "Read Markdown file",
      text: "Content",
    };
    const css = `.rm-dsh{color:var(--dsw-alias-label-primary);border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-1);border-radius:12px;margin:8px 0;overflow:hidden;font-size:12px}.rm-dsh *{box-sizing:border-box}.rm-dsh header,.rm-dsh .rm-row{display:flex;align-items:center;gap:8px}.rm-dsh header{padding:10px 12px;border-bottom:1px solid var(--dsw-alias-border-l1)}.rm-dsh header strong{flex:1;letter-spacing:.06em;font-family:'OCR A Extended',monospace}.rm-dsh button{position:relative;background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary);border:1px solid var(--dsw-alias-border-l2);border-radius:6px;padding:6px 9px;cursor:pointer;transition:background .3s,border-color .3s;overflow:hidden}.rm-dsh button:hover{background:var(--dsw-alias-interactive-bg-hover);border-color:var(--dsw-alias-brand-primary)}.rm-dsh button:focus-visible,.rm-dsh input:focus-visible,.rm-dsh textarea:focus-visible{outline:2px solid var(--dsw-alias-brand-primary);outline-offset:2px}.rm-dsh button::after{content:'';position:absolute;inset:-50% -100%;background:linear-gradient(110deg,transparent 42%,var(--dsw-alias-border-l4) 50%,transparent 58%);transform:translateX(-50%);opacity:0;pointer-events:none}.rm-dsh button:hover::after{opacity:.5;animation:rm-dsh-flow 4.8s linear infinite}.rm-dsh button:disabled{opacity:.45;cursor:wait}.rm-dsh nav{display:flex;gap:5px;padding:10px 12px;overflow-x:auto}.rm-dsh nav>div{display:flex;flex-shrink:0;gap:2px}.rm-dsh button[aria-selected=true]{border-color:var(--dsw-alias-brand-primary);color:var(--dsw-alias-brand-primary)}.rm-dsh .rm-content{padding:0 12px 12px;max-height:480px;overflow:auto}.rm-dsh input,.rm-dsh textarea,.rm-dsh select{width:100%;border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary);border-radius:6px;padding:7px;font:inherit}.rm-dsh textarea{resize:vertical;min-height:70px}.rm-dsh label{display:grid;gap:5px;margin:9px 0;color:var(--dsw-alias-label-secondary)}.rm-dsh .rm-main{display:grid;grid-template-columns:minmax(0,1fr) minmax(180px,.8fr);gap:14px}.rm-dsh .rm-spec{border-left:1px solid var(--dsw-alias-border-l1);padding-left:12px;max-height:290px;overflow:auto}.rm-dsh .rm-spec h4{font-weight:500;margin:10px 0 5px;color:var(--dsw-alias-label-secondary)}.rm-dsh ul{padding-left:18px;margin:5px 0}.rm-dsh li{margin:5px 0;overflow-wrap:anywhere}.rm-dsh small{color:var(--dsw-alias-label-tertiary)}.rm-dsh .rm-feedback{padding:6px 12px;overflow-wrap:anywhere;color:var(--dsw-alias-label-secondary)}.rm-dsh .rm-error{color:var(--dsw-alias-state-error-primary)}.rm-dsh .rm-choice{border:1px solid var(--dsw-alias-brand-primary);padding:10px;border-radius:8px;margin-bottom:10px}.rm-dsh .rm-choice .rm-row{flex-wrap:wrap}.rm-dsh pre{white-space:pre-wrap;max-height:200px;overflow:auto;font-size:11px}.rm-dsh details{margin-top:10px}.rm-dsh summary{cursor:pointer;color:var(--dsw-alias-label-secondary)}.rm-dsh .rm-skill{padding:7px 0;border-bottom:1px solid var(--dsw-alias-border-l1)}@keyframes rm-dsh-flow{to{transform:translateX(50%)}}@media(prefers-reduced-motion:reduce){.rm-dsh button:hover::after{animation:none}}@media(max-width:650px){.rm-dsh .rm-main{grid-template-columns:1fr}.rm-dsh .rm-spec{border-left:0;border-top:1px solid var(--dsw-alias-border-l1);padding-left:0}}`;
    return {
      inject: ["slots", "remote", "remote.commands", "locale"],
      apply(ctx) {
        ctx.effect(() => ctx.locale.register("robomaster", { zh, en }));
        const t = ctx.locale.bind("robomaster");
        function Panel({ sessionId, useSession }) {
          const [opened, setOpened] = React.useState(false),
            dialog = React.useRef(null);
          React.useEffect(() => {
            if (opened && !dialog.current?.open) dialog.current?.showModal();
            if (!opened && dialog.current?.open) dialog.current.close();
          }, [opened]);
          const [state, setState] = React.useState(null),
            [busy, setBusy] = React.useState(false),
            [feedback, setFeedback] = React.useState(""),
            [error, setError] = React.useState(false),
            [page, setPage] = React.useState("work"),
            [collapsed, setCollapsed] = React.useState(false);
          const [draft, setDraft] = React.useState(""),
            [config, setConfig] = React.useState({}),
            [specText, setSpecText] = React.useState(""),
            [specSource, setSpecSource] = React.useState(""),
            [section, setSection] = React.useState("requirements");
          const [query, setQuery] = React.useState(""),
            [results, setResults] = React.useState(null),
            [skillName, setSkillName] = React.useState(""),
            [skillBody, setSkillBody] = React.useState("");
          const alive = React.useRef(true),
            sessionRef = React.useRef(sessionId);
          sessionRef.current = sessionId;
          const running = useSession((s) => s.running) ?? false;
          const request = React.useCallback(
            async (request) => {
              const answer = await ctx.remote.commands.execute(
                sessionId,
                `/robomaster ${JSON.stringify(request)}`,
                [],
              );
              if (!answer.ok) throw Error(answer.error.message);
              const result = answer.value?.result;
              if (result?.kind !== "success")
                throw Error(result?.text || t("error"));
              return JSON.parse(result.text);
            },
            [sessionId],
          );
          const refresh = React.useCallback(async () => {
            const id = sessionId;
            const p = await request({ action: "snapshot" });
            if (alive.current && sessionRef.current === id) {
              setState(p);
              setConfig({
                workspace: p.workspace,
                mcpPython: p.mcpPython,
                mcpServer: p.mcpServer,
                ragUrl: p.ragUrl,
                prompts: { ...p.prompts },
              });
            }
            return p;
          }, [sessionId, request]);
          React.useEffect(() => {
            alive.current = true;
            setState(null);
            setFeedback("");
            setDraft("");
            refresh().catch((e) => {
              if (alive.current) {
                setError(true);
                setFeedback(e.message);
              }
            });
            return () => {
              alive.current = false;
            };
          }, [sessionId]);
          React.useEffect(() => {
            if (!running)
              refresh().catch((e) => {
                if (alive.current) {
                  setError(true);
                  setFeedback(e.message);
                }
              });
          }, [running, refresh]);
          async function act(requestBody, success = t("saved")) {
            setBusy(true);
            setError(false);
            const id = sessionId;
            try {
              const value = await request(requestBody);
              if (alive.current && sessionRef.current === id) {
                await refresh();
                setFeedback(success);
              }
              return value;
            } catch (e) {
              if (alive.current && sessionRef.current === id) {
                setError(true);
                setFeedback(e.message);
              }
              return null;
            } finally {
              if (alive.current && sessionRef.current === id) setBusy(false);
            }
          }
          const button = (label, onClick, props = {}) =>
            h(
              "button",
              { type: "button", disabled: busy, onClick, ...props },
              label,
            );
          const label = (key, value, onChange, props = {}) =>
            h(
              "label",
              null,
              t(key),
              h("input", {
                value: value || "",
                onChange: (e) => onChange(e.target.value),
                ...props,
              }),
            );
          const stage = state?.stage || "requirements";
          const content = h(
            "section",
            { className: "rm-dsh", "aria-label": t("title") },
            h("style", null, css),
            h(
              "header",
              null,
              h(
                "svg",
                {
                  viewBox: "0 0 40 40",
                  width: 26,
                  height: 26,
                  "aria-hidden": true,
                  fill: "none",
                  stroke: "currentColor",
                },
                h("path", {
                  d: "M20 3 35 12 20 21 5 12ZM5 22l15 9 15-9M5 31l15 7 15-7M20 21v10",
                }),
              ),
              h("strong", null, "ROBOMASTER / STUDIO"),
              button(t("refresh"), () => act({ action: "snapshot" })),
              button(
                t("settings"),
                () => setPage(page === "settings" ? "work" : "settings"),
                { "aria-pressed": page === "settings" },
              ),
              button(
                t(collapsed ? "expand" : "collapse"),
                () => setCollapsed(!collapsed),
                { "aria-expanded": !collapsed },
              ),
            ),
            !collapsed &&
              state &&
              h(
                React.Fragment,
                null,
                h(
                  "nav",
                  { "aria-label": t("title") },
                  ...state.tabs.map((tab) =>
                    h(
                      "div",
                      { key: tab.id },
                      button(
                        `${t(tab.stage)}${tab.ordinal > 1 ? " " + tab.ordinal : ""}`,
                        () => act({ action: "tab_select", id: tab.id }),
                        {
                          "aria-selected": tab.id === state.activeTab,
                          disabled: busy || running,
                        },
                      ),
                      button(
                        "+",
                        () => act({ action: "tab_add", stage: tab.stage }),
                        {
                          "aria-label": `${t("add")} ${t(tab.stage)}`,
                          disabled: busy || running,
                        },
                      ),
                      state.tabs.filter((x) => x.stage === tab.stage).length >
                        1 &&
                        button(
                          "×",
                          () => act({ action: "tab_close", id: tab.id }),
                          {
                            "aria-label": `${t("close")} ${t(tab.stage)} ${tab.ordinal}`,
                            disabled: busy || running,
                          },
                        ),
                    ),
                  ),
                ),
                h(
                  "div",
                  { className: "rm-content" },
                  state.pending &&
                    h(
                      "div",
                      { className: "rm-choice" },
                      h("small", null, t("choose")),
                      h("p", null, state.pending.question),
                      h(
                        "div",
                        { className: "rm-row" },
                        ...state.pending.options.map((choice) =>
                          button(choice, () =>
                            act(
                              {
                                action: "answer",
                                id: state.pending.id,
                                choice,
                              },
                              t("sent"),
                            ),
                          ),
                        ),
                      ),
                    ),
                  page === "settings"
                    ? h(
                        React.Fragment,
                        null,
                        label("workspace", config.workspace, (v) =>
                          setConfig({ ...config, workspace: v }),
                        ),
                        h(
                          "details",
                          null,
                          h("summary", null, "SolidWorks MCP"),
                          label("mcpPython", config.mcpPython, (v) =>
                            setConfig({ ...config, mcpPython: v }),
                          ),
                          label("mcpServer", config.mcpServer, (v) =>
                            setConfig({ ...config, mcpServer: v }),
                          ),
                          label("rag", config.ragUrl, (v) =>
                            setConfig({ ...config, ragUrl: v }),
                          ),
                        ),
                        h(
                          "label",
                          null,
                          t("prompt"),
                          h("textarea", {
                            value: config.prompts?.[stage] || "",
                            onChange: (e) =>
                              setConfig({
                                ...config,
                                prompts: {
                                  ...config.prompts,
                                  [stage]: e.target.value,
                                },
                              }),
                          }),
                        ),
                        h(
                          "div",
                          { className: "rm-row" },
                          button(
                            t("save"),
                            () => act({ action: "configure", ...config }),
                            { disabled: busy || running },
                          ),
                          button(t("mcp"), () => act({ action: "check_mcp" })),
                        ),
                        h(
                          "details",
                          null,
                          h("summary", null, t("memory")),
                          h("p", null, state.summary || t("empty")),
                          button(
                            t("summarize"),
                            () =>
                              act(
                                { action: "send", text: t("summaryPrompt") },
                                t("sent"),
                              ),
                            { disabled: busy || running || !!state.pending },
                          ),
                          ...state.skills.map((skill) =>
                            h(
                              "div",
                              { className: "rm-skill", key: skill.id },
                              h(
                                "div",
                                { className: "rm-row" },
                                h("strong", null, skill.name),
                                h("small", null, skill.status),
                                button(
                                  t(skill.enabled ? "disable" : "enable"),
                                  () =>
                                    act({
                                      action: "skill_enable",
                                      id: skill.id,
                                      enabled: !skill.enabled,
                                    }),
                                  { disabled: busy || running },
                                ),
                              ),
                              h(
                                "details",
                                null,
                                h("summary", null, t("text")),
                                h("pre", null, skill.body),
                              ),
                            ),
                          ),
                          label("skillName", skillName, setSkillName),
                          h(
                            "label",
                            null,
                            t("skillBody"),
                            h("textarea", {
                              value: skillBody,
                              onChange: (e) => setSkillBody(e.target.value),
                            }),
                          ),
                          h(
                            "label",
                            null,
                            t("file"),
                            h("input", {
                              type: "file",
                              accept: ".md,.txt",
                              onChange: async (e) => {
                                const f = e.target.files?.[0];
                                if (!f) return;
                                if (f.size > 150000) {
                                  setError(true);
                                  setFeedback("150 KB max");
                                  return;
                                }
                                setSkillBody(await f.text());
                                if (!skillName)
                                  setSkillName(
                                    f.name.replace(/\.(md|txt)$/i, ""),
                                  );
                              },
                            }),
                          ),
                          button(
                            t("import"),
                            () =>
                              act({
                                action: "skill_import",
                                name: skillName,
                                body: skillBody,
                              }),
                            { disabled: busy || running },
                          ),
                        ),
                      )
                    : h(
                        "div",
                        { className: "rm-main" },
                        h(
                          "div",
                          null,
                          stage === "reuse" &&
                            h(
                              React.Fragment,
                              null,
                              label("query", query, setQuery),
                              h(
                                "div",
                                { className: "rm-row" },
                                ...["local", "step"].map((source) =>
                                  button(t(source), async () => {
                                    const r = await act({
                                      action: "search",
                                      source,
                                      query,
                                    });
                                    if (r) setResults(r);
                                  }),
                                ),
                              ),
                              results &&
                                h(
                                  "pre",
                                  null,
                                  JSON.stringify(results, null, 2),
                                ),
                            ),
                          stage === "modeling" &&
                            h(
                              "div",
                              null,
                              h("small", null, t("iterations")),
                              state.iterations.length
                                ? h(
                                    "ol",
                                    null,
                                    ...state.iterations.map((i) =>
                                      h(
                                        "li",
                                        { key: i.id },
                                        `${i.title} / ${i.status}`,
                                        i.evidence &&
                                          h(
                                            "details",
                                            null,
                                            h("summary", null, t("source")),
                                            h("pre", null, i.evidence),
                                          ),
                                      ),
                                    ),
                                  )
                                : h("p", null, t("noIterations")),
                            ),
                          stage === "mates"
                            ? button(
                                t("start"),
                                () =>
                                  act(
                                    {
                                      action: "send",
                                      text: state.prompts.mates,
                                    },
                                    t("sent"),
                                  ),
                                {
                                  disabled: busy || running || !!state.pending,
                                },
                              )
                            : h(
                                React.Fragment,
                                null,
                                h(
                                  "label",
                                  null,
                                  t(stage),
                                  h("textarea", {
                                    placeholder: t("input"),
                                    value: draft,
                                    onChange: (e) => setDraft(e.target.value),
                                    disabled:
                                      busy || running || !!state.pending,
                                  }),
                                ),
                                button(
                                  t("send"),
                                  async () => {
                                    if (
                                      await act(
                                        { action: "send", text: draft },
                                        t("sent"),
                                      )
                                    )
                                      setDraft("");
                                  },
                                  {
                                    disabled:
                                      busy ||
                                      running ||
                                      !!state.pending ||
                                      !draft.trim(),
                                  },
                                ),
                              ),
                          h("small", null, state.workspace || t("workspace")),
                        ),
                        h(
                          "aside",
                          { className: "rm-spec", "aria-label": t("spec") },
                          ...sections.map((key) =>
                            h(
                              "div",
                              { key },
                              h("h4", null, t(key)),
                              h(
                                "ul",
                                null,
                                ...state.spec[key].map((item) =>
                                  h(
                                    "li",
                                    { key: item.id, title: item.source },
                                    item.text,
                                  ),
                                ),
                              ),
                            ),
                          ),
                          h(
                            "details",
                            null,
                            h("summary", null, t("newSpec")),
                            h(
                              "select",
                              {
                                value: section,
                                onChange: (e) => setSection(e.target.value),
                                "aria-label": t("spec"),
                              },
                              ...sections.map((key) =>
                                h("option", { value: key, key }, t(key)),
                              ),
                            ),
                            label("text", specText, setSpecText),
                            label("source", specSource, setSpecSource),
                            button(
                              t("add"),
                              async () => {
                                if (
                                  await act({
                                    action: "spec_add",
                                    section,
                                    text: specText,
                                    source: specSource,
                                  })
                                ) {
                                  setSpecText("");
                                  setSpecSource("");
                                }
                              },
                              { disabled: busy || running || !specText.trim() },
                            ),
                          ),
                        ),
                      ),
                ),
              ),
            (feedback || busy) &&
              h(
                "div",
                {
                  className: `rm-feedback ${error ? "rm-error" : ""}`,
                  role: error ? "alert" : "status",
                },
                busy ? t("wait") : feedback,
              ),
          );
          return h(
            React.Fragment,
            null,
            h(
              "style",
              null,
              css +
                `.rm-dsh-entry{flex:none;margin:6px 0}.rm-dsh-entry header{border:0}.rm-dsh-dialog{width:min(1120px,94vw);max-width:94vw;height:min(780px,90vh);max-height:90vh;padding:0;border:1px solid var(--dsw-alias-border-l2);border-radius:12px;background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);overflow:auto}.rm-dsh-dialog::backdrop{background:color-mix(in srgb,var(--dsw-alias-label-primary) 28%,transparent)}.rm-dsh-dialog>.rm-dsh{border:0;margin:0;overflow:visible}.rm-dsh-dialog .rm-content{max-height:none}.rm-dsh-dialog .rm-spec{max-height:480px}.rm-dsh-dialog .rm-main{min-height:380px}.rm-dsh-dialog .rm-main textarea{min-height:150px}.rm-dsh-dialog .rm-dialog-close{display:flex;justify-content:flex-end;padding:8px 12px;border-bottom:1px solid var(--dsw-alias-border-l1)}.rm-dsh-dialog,.rm-dsh-entry{font-family:'OCR A Extended','Noto Sans SC',sans-serif}.rm-dsh-dialog button{font-family:inherit}.rm-dsh-entry small{margin-right:8px}`,
            ),
            h(
              "section",
              { className: "rm-dsh rm-dsh-entry" },
              h(
                "header",
                null,
                h("strong", null, "ROBOMASTER / STUDIO"),
                h("small", null, t(stage)),
                button(t("expand"), () => setOpened(true), {
                  "aria-haspopup": "dialog",
                  "aria-expanded": opened,
                }),
              ),
            ),
            h(
              "dialog",
              {
                ref: dialog,
                className: "rm-dsh-dialog",
                "aria-label": t("title"),
                onCancel: () => setOpened(false),
                onClose: () => setOpened(false),
              },
              h(
                "div",
                { className: "rm-dsh rm-dialog-close" },
                button(t("close"), () => setOpened(false)),
              ),
              content,
            ),
          );
        }
        ctx.slots.inject("conversation.input.dock", () =>
          ctx.slots.register(
            {
              name: "conversation.input.dock",
              id: "robomaster-studio",
              order: 5,
              locale: "robomaster",
            },
            Panel,
          ),
        );
      },
    };
  },
});
