import { readFileSync, writeFileSync } from "node:fs";
const source = readFileSync(
  new URL("../src-tauri/src/domain.rs", import.meta.url),
  "utf8",
);
const prompts = Object.fromEntries(
  [
    ...source.matchAll(
      /\("(requirements|reuse|prototype|modeling|mates)","([^"]+)"\)/g,
    ),
  ].map((m) => [m[1], m[2]]),
);
if (Object.keys(prompts).length !== 5)
  throw Error("Cannot extract the five shared stage prompts");
const block = source.split("pub fn tool_allowed")[1].split("#[cfg(test)]")[0];
const prototype = [
  ...block.split("name.starts_with")[0].matchAll(/"(solidworks_[^"]+)"/g),
].map((m) => m[1]);
const excluded = [
  ...block.split("name.starts_with")[1].matchAll(/"(solidworks_[^"]+)"/g),
].map((m) => m[1]);
writeFileSync(
  new URL("../plugins/dsh/workflow.json", import.meta.url),
  JSON.stringify({ prompts, prototype, excluded }, null, 2) + "\n",
);
