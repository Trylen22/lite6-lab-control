/* UFACTORY Studio project files for the Lab tab.
 *
 * Studio exports a project as a .tar.gz holding:
 *   ./.app                         {"deviceType": "lite6", "lastAccessTime": …}
 *   ./app.xml                      the Blockly workspace
 *   ./app_location_variable.json   editor view state + variables
 * This reads those archives (or a bare app.xml) and writes the same layout,
 * so a program built here opens in Studio and the reverse. Studio-only
 * editor buttons (btn_move, btn_edit, btn_set_color) are removed on import
 * and put back on export. Blocks the simulator doesn't know are kept intact
 * inside a placeholder and restored on export.
 */
(function () {
  "use strict";
  const NS = "https://developers.google.com/blockly/xml";
  const enc = new TextEncoder();
  const dec = new TextDecoder();

  async function gunzip(bytes) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }
  async function gzip(bytes) {
    const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream("gzip"));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }

  function untar(bytes) {
    const files = {};
    let off = 0;
    while (off + 512 <= bytes.length) {
      const header = bytes.subarray(off, off + 512);
      if (header.every((b) => b === 0)) break;
      const name = dec.decode(header.subarray(0, 100)).replace(/\0.*$/s, "");
      const prefix = dec.decode(header.subarray(345, 500)).replace(/\0.*$/s, "");
      const size = parseInt(dec.decode(header.subarray(124, 136)).replace(/\0.*$/s, "").trim() || "0", 8);
      const type = String.fromCharCode(header[156] || 48);
      const path = (prefix ? prefix + "/" : "") + name;
      if (type === "0" || type === "\0") files[path.replace(/^\.\//, "")] = bytes.slice(off + 512, off + 512 + size);
      off += 512 + Math.ceil(size / 512) * 512;
    }
    return files;
  }

  function tarEntry(name, data) {
    const header = new Uint8Array(512);
    const put = (text, at, len) => header.set(enc.encode(text).subarray(0, len), at);
    const octal = (n, len) => n.toString(8).padStart(len - 1, "0") + "\0";
    put(name, 0, 100);
    put(octal(0o644, 8), 100, 8);
    put(octal(1000, 8), 108, 8);
    put(octal(1000, 8), 116, 8);
    put(octal(data.length, 12), 124, 12);
    put(octal(Math.floor(Date.now() / 1000), 12), 136, 12);
    put("        ", 148, 8);
    header[156] = 48; // regular file
    put("ustar\0", 257, 6);
    put("00", 263, 2);
    put("uf", 265, 32);
    put("uf", 297, 32);
    let sum = 0;
    for (const b of header) sum += b;
    put(sum.toString(8).padStart(6, "0") + "\0 ", 148, 8);
    const padded = new Uint8Array(Math.ceil(data.length / 512) * 512);
    padded.set(data);
    return [header, padded];
  }

  function tar(files) {
    const parts = [];
    for (const [name, data] of Object.entries(files)) parts.push(...tarEntry(name, data));
    parts.push(new Uint8Array(1024));
    const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
    let off = 0;
    for (const p of parts) {
      out.set(p, off);
      off += p.length;
    }
    return out;
  }

  /** File → { xml, deviceType } */
  async function readProject(file) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (/\.xml$/i.test(file.name)) return { xml: dec.decode(bytes), deviceType: null };
    const files = untar(bytes[0] === 0x1f && bytes[1] === 0x8b ? await gunzip(bytes) : bytes);
    const xml = files["app.xml"];
    if (!xml) throw new Error("No app.xml inside this archive; is it a Studio project?");
    let deviceType = null;
    try {
      deviceType = JSON.parse(dec.decode(files[".app"])).deviceType;
    } catch (_) {}
    return { xml: dec.decode(xml), deviceType };
  }

  /** Studio XML text → Blockly DOM the Lab can load (+ list of kept unknown types). */
  function importDom(xmlText, knownTypes) {
    const doc = new DOMParser().parseFromString(xmlText, "text/xml");
    if (doc.querySelector("parsererror")) throw new Error("This file isn't valid Blockly XML");
    for (const v of [...doc.getElementsByTagNameNS(NS, "value")])
      if (v.getAttribute("name")?.startsWith("btn_")) v.remove();
    const unknown = new Set();
    for (const block of [...doc.getElementsByTagNameNS(NS, "block")]) {
      const type = block.getAttribute("type");
      if (knownTypes.has(type)) continue;
      unknown.add(type);
      // Keep the original (minus its <next> chain) for export.
      const next = [...block.children].find((c) => c.localName === "next");
      if (next) next.remove();
      const original = new XMLSerializer().serializeToString(block);
      const holder = doc.createElementNS(NS, "block");
      holder.setAttribute("type", "lab_unsupported");
      for (const a of ["id", "x", "y"]) if (block.hasAttribute(a)) holder.setAttribute(a, block.getAttribute(a));
      const field = doc.createElementNS(NS, "field");
      field.setAttribute("name", "TYPE");
      field.textContent = type;
      const data = doc.createElementNS(NS, "data");
      data.textContent = original;
      holder.append(field, data);
      if (next) holder.append(next);
      block.replaceWith(holder);
    }
    return { dom: doc.documentElement, unknown: [...unknown] };
  }

  /** Blockly DOM from the workspace → Studio XML text. */
  function exportXml(dom) {
    const doc = dom.ownerDocument;
    const rand = () => Math.random().toString(36).slice(2, 12);
    const button = (name) => {
      const v = doc.createElementNS(NS, "value");
      v.setAttribute("name", name);
      const b = doc.createElementNS(NS, "block");
      b.setAttribute("type", name);
      b.setAttribute("id", rand());
      v.append(b);
      return v;
    };
    for (const block of [...dom.getElementsByTagNameNS(NS, "block")]) {
      const type = block.getAttribute("type");
      const next = [...block.children].find((c) => c.localName === "next");
      if (type === "move_joints" || type === "move_cartesian") block.insertBefore(button("btn_move"), next || null), block.insertBefore(button("btn_edit"), next || null);
      if (type === "set_suction_cup") block.insertBefore(button("btn_set_color"), next || null);
      if (type === "lab_unsupported") {
        const data = [...block.children].find((c) => c.localName === "data");
        if (!data) continue;
        const original = new DOMParser().parseFromString(data.textContent, "text/xml").documentElement;
        const restored = doc.importNode(original, true);
        for (const a of ["x", "y"]) if (block.hasAttribute(a)) restored.setAttribute(a, block.getAttribute(a));
        if (next) restored.append(next);
        block.replaceWith(restored);
      }
    }
    dom.setAttribute("xmlns", NS);
    return new XMLSerializer().serializeToString(dom);
  }

  async function writeProject(xmlText) {
    const files = {
      "./.app": enc.encode(JSON.stringify({ deviceType: "lite6", lastAccessTime: Date.now() / 1000 }, null, 4)),
      "./app.xml": enc.encode(xmlText),
      "./app_location_variable.json": enc.encode(
        JSON.stringify({ SettingVar: { scale: 0.7, scrollx: 0, scrolly: 0, variable: {} } }, null, 4),
      ),
    };
    return new Blob([await gzip(tar(files))], { type: "application/gzip" });
  }

  window.StudioFile = { readProject, importDom, exportXml, writeProject, untar, tar };
})();
