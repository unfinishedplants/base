import fs from "fs";
import path from "path";
import { extractCleanDescription } from "../custom-plugins/description-cleaner.js";

const contentDir = "./content";
const files = fs.readdirSync(contentDir).filter(f => f.endsWith(".md") && f !== "index.md");

function extractArticleMetadata(fileContent) {
  const fmMatch = fileContent.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  let rawTitle = "";
  let title = "";
  let slug = "";
  let date = "";
  let description = "";

  if (fmMatch) {
    const lines = fmMatch[1].split("\n");
    for (const l of lines) {
      if (l.startsWith("title:")) {
        rawTitle = l.replace(/^title:\s*["']?/, "").replace(/["']?\s*$/, "");
        title = rawTitle.replace(/^リークログ（後編）｜/, "").replace(/^リークログ（前編）｜/, "").replace(/^リークログ｜/, "");
      }
      if (l.startsWith("slug:")) slug = l.replace(/^slug:\s*/, "").trim();
      if (l.startsWith("date:")) date = l.replace(/^date:\s*/, "").trim();
      if (l.startsWith("description:")) description = l.replace(/^description:\s*["']?/, "").replace(/["']?\s*$/, "");
      if (l.startsWith("socialDescription:")) description = l.replace(/^socialDescription:\s*["']?/, "").replace(/["']?\s*$/, "");
    }
  }

  const body = fileContent.replace(/^---\r?\n[\s\S]*?\r?\n---/, "");
  const desc = extractCleanDescription(body, description, 160);

  return { rawTitle, title, slug, date, desc };
}

const articles = [];
for (const f of files) {
  const content = fs.readFileSync(path.join(contentDir, f), "utf8");
  const extracted = extractArticleMetadata(content);
  articles.push(extracted);
}

articles.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

console.log(`Processed ${articles.length} articles:`);
for (const a of articles) {
  console.log(`- [${a.date} ${a.title}](https://ghost.voronoi.works/${a.slug}): ${a.desc}`);
}
