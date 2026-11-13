import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, symlink } from "node:fs/promises";
import path from "node:path";
import { StudioService, toolAllowed } from "../plugins/dsh/service.js";
import { toolArguments } from "../plugins/dsh/mcp.js";

test("DSH projects persist, stage authority and pending choices remain user-only", async () => {
  const root = await mkdtemp(path.resolve(".local/dsh-unit-"));
  const service = new StudioService({
    dataDirectory: path.join(root, "state"),
  });
  const injected = [],
    queued = [],
    agent = {
      id: "session-one",
      status: "idle",
      inject: (m) => injected.push(m),
      followup: (m) => queued.push(m),
    };
  const user = { user: true };
  try {
    let p = await service.operate(agent, { action: "snapshot" });
    assert.equal(p.tabs.length, 5);
    await assert.rejects(
      service.operate(agent, { action: "stage", stage: "modeling" }),
      /用户/,
    );
    await service.operate(
      agent,
      { action: "configure", workspace: path.join(root, "models") },
      user,
    );
    await service.operate(agent, {
      action: "spec_add",
      section: "requirements",
      text: "底盘宽度 400 mm",
    });
    await assert.rejects(
      service.operate(agent, {
        action: "spec_add",
        section: "verifiedParts",
        text: "电机 5 N·m",
      }),
      /来源/,
    );
    await service.operate(
      agent,
      { action: "tab_add", stage: "requirements" },
      user,
    );
    p = await service.operate(agent, { action: "snapshot" });
    await service.operate(
      agent,
      { action: "tab_close", id: p.tabs.at(-1).id },
      user,
    );
    await assert.rejects(
      service.operate(agent, { action: "tab_close", id: p.tabs[0].id }, user),
      /至少保留/,
    );
    await service.operate(agent, { action: "stage", stage: "prototype" }, user);
    await assert.rejects(
      service.operate(agent, {
        action: "cad_call",
        name: "solidworks_detect_interference",
        arguments: {},
      }),
      /禁止/,
    );
    await assert.rejects(
      service.operate(agent, {
        action: "iteration",
        status: "passed",
        text: "通过",
        evidence: "假设",
      }),
      /不执行验收/,
    );
    const question = await service.operate(agent, {
      action: "ask_user",
      text: "选择轮径",
      options: ["100 mm", "125 mm"],
    });
    await assert.rejects(
      service.operate(agent, {
        action: "answer",
        id: question.id,
        choice: "100 mm",
      }),
      /用户/,
    );
    await assert.rejects(
      service.operate(agent, {
        action: "cad_call",
        name: "solidworks_bounding_box",
        arguments: {},
      }),
      /等待用户/,
    );
    await assert.rejects(
      service.operate(
        agent,
        { action: "answer", id: "stale", choice: "100 mm" },
        user,
      ),
      /变化/,
    );
    await service.operate(
      agent,
      { action: "answer", id: question.id, choice: "100 mm" },
      user,
    );
    assert.equal(queued.length, 1);
    assert.match(queued[0].content[0].text, /100 mm/);
    await service.operate(agent, {
      action: "skill_save",
      name: "安装步骤",
      body: "仅测试草稿",
    });
    const restored = new StudioService({
      dataDirectory: path.join(root, "state"),
    });
    p = await restored.operate(agent, { action: "snapshot" });
    assert.equal(p.pending, null);
    assert.equal(p.spec.requirements[0].text, "底盘宽度 400 mm");
    assert.equal(p.skills[0].status, "preference");
    assert.equal(p.skills[1].enabled, false);
    restored.close();
    await assert.rejects(
      service.operate(
        { ...agent, id: "another" },
        { action: "cad_call", name: "solidworks_new_document" },
      ),
      /禁止/,
    );
    assert.ok(injected.length >= 2);
    assert.equal(
      new Set([...injected, ...queued].map((m) => m.id)).size,
      injected.length + queued.length,
    );
    assert.ok(
      [...injected, ...queued].every(
        (m) => m.role === "user" && typeof m.id === "string",
      ),
    );
  } finally {
    service.close();
    await rm(root, { recursive: true, force: true });
  }
});
test("CAD paths reject traversal, old workspace and junction escape", async () => {
  const root = await mkdtemp(path.resolve(".local/dsh-path-"));
  const models = path.join(root, "models"),
    outside = path.join(root, "outside");
  await mkdir(models);
  await mkdir(outside);
  try {
    assert.equal(
      (
        await toolArguments(models, "solidworks_save_document", {
          path: "测试.sldprt",
        })
      ).path,
      path.join(models, "测试.sldprt"),
    );
    await assert.rejects(
      toolArguments(models, "solidworks_save_document", {}),
      /新文件名/,
    );
    await assert.rejects(
      toolArguments(models, "solidworks_save_document", {
        path: "../escape.sldprt",
      }),
      /超出/,
    );
    await assert.rejects(
      toolArguments(models, "solidworks_export_active", {
        output_path: path.join(outside, "a.step"),
      }),
      /超出/,
    );
    await symlink(outside, path.join(models, "redirect"), "junction");
    await assert.rejects(
      toolArguments(models, "solidworks_save_document", {
        path: "redirect/escape.sldprt",
      }),
      /链接/,
    );
    assert.equal(toolAllowed("requirements", "solidworks_connect"), false);
    assert.equal(toolAllowed("prototype", "solidworks_bounding_box"), true);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
