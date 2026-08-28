export function cleanDescriptionText(raw) {
  if (!raw) return "";
  let t = raw
    // Remove image syntax / unparsed image tags / wikilinks images
    .replace(/!\[\[.*?\]\]/g, "")
    .replace(/!\[.*?\]\(.*?\)/g, "")
    .replace(/!\[.*?\]/g, "")
    .replace(/未検出画像:[^\]\)\n]*/g, "")
    // Strip markdown links [text](url) -> text
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    // Strip markdown headings
    .replace(/^#+\s+.*$/gm, "")
    // Strip blockquotes/pointers
    .replace(/^>\s*/gm, "")
    .replace(/^[👉🔗🤖📦⚡️🛠️\s]+/gm, "")
    // Strip bold/italics/code
    .replace(/[*_~`]/g, "")
    .replace(/\\/g, "")
    // Normalize spaces
    .replace(/\s+/g, " ")
    .trim();

  // If starts with "ひぎィィィッ！！！", strip it if followed by meaningful text
  t = t.replace(/^ひぎィィィッ[！!]*\s*/, "");

  return t;
}

export function extractCleanDescription(rawText, frontmatterDescription, targetLen = 160) {
  if (frontmatterDescription && frontmatterDescription.trim()) {
    return cleanDescriptionText(frontmatterDescription.trim());
  }

  const cleaned = cleanDescriptionText(rawText);
  if (!cleaned) return "";

  if (cleaned.length <= targetLen) {
    return cleaned;
  }

  const sub = cleaned.slice(0, targetLen + 20);
  const lastPeriod = Math.max(
    sub.lastIndexOf("。"),
    sub.lastIndexOf("！"),
    sub.lastIndexOf("？"),
    sub.lastIndexOf(". "),
    sub.lastIndexOf("! "),
    sub.lastIndexOf("? ")
  );

  if (lastPeriod >= 80 && lastPeriod <= targetLen + 15) {
    return sub.slice(0, lastPeriod + 1).trim();
  } else {
    return cleaned.slice(0, targetLen).trim() + "...";
  }
}
