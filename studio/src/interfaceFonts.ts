import { invoke, isTauri } from "@tauri-apps/api/core";

// Load the user's installed fonts directly: WebView's system font collection can
// be stale after installation. Font files are never copied into a release.
export async function loadInterfaceFonts() {
  if (!isTauri()) return;
  const faces = [
    { id: "ocr", family: "Studio OCR A", descriptors: { weight: "400" } },
    {
      id: "noto",
      family: "Studio Noto Thin",
      descriptors: { weight: "100 900", variationSettings: '"wght" 100' },
    },
  ];
  const results = await Promise.allSettled(
    faces.map(async ({ id, family, descriptors }) => {
      const bytes = await invoke<ArrayBuffer | number[]>(
        "load_interface_font",
        {
          name: id,
        },
      );
      const face = new FontFace(
        family,
        bytes instanceof ArrayBuffer ? bytes : new Uint8Array(bytes),
        descriptors,
      );
      await face.load();
      document.fonts.add(face);
    }),
  );
  document.documentElement.dataset.interfaceFonts = results
    .map(
      (result, index) =>
        `${faces[index].id}:${result.status === "fulfilled" ? "loaded" : "fallback"}`,
    )
    .join(" ");
}
