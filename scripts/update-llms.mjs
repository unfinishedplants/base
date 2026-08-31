import fs from "fs";
import path from "path";
import { extractCleanDescription } from "../custom-plugins/description-cleaner.js";

const contentDir = "./content";
const files = fs.readdirSync(contentDir).filter(f => f.endsWith(".md") && f !== "index.md");

function extractArticleMetadata(fileContent, fileName) {
  fileContent = fileContent.replace(/^\uFEFF/, "");
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

  if (!description.trim()) {
    throw new Error(`Missing explicit description: content/${fileName}`);
  }

  const body = fileContent.replace(/^---\r?\n[\s\S]*?\r?\n---/, "");
  const desc = extractCleanDescription(body, description, 160);

  return { rawTitle, title, slug, date, desc };
}

const articles = [];
for (const f of files) {
  const content = fs.readFileSync(path.join(contentDir, f), "utf8");
  const extracted = extractArticleMetadata(content, f);
  articles.push(extracted);
}

articles.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

const llmsContent = `# Ghost in the Voronoi

> Ghost in the Voronoi (ghost.voronoi.works) は、AIと人間の共創、自律協働エージェント、身体性と認知の境界、プロンプトエンジニアリングの動態論を探求する実践的思考・観測ログ（リークログ）のデジタルガーデンです。

## 主要テーマ / Key Topics
- **AI哲学・動態論**: ブレイブメンロードモデル、主体性と外部化、言葉の余白とノイズ、身体性の拡張
- **自律協働エージェント実務**: 多段階蒸留思考、防波堤マスキング配管、YuRelay（マルチエージェント協働構造体）
- **ハードウェア・身体性**: 3Dプリント義手、電脳樹皮（Cyber-Bark）、マタギドライブ、内面観測

## 観測ログ一覧 / Observation Logs (${articles.length} articles)
` + articles.map(a => `- [${a.date} ${a.title}](https://ghost.voronoi.works/${a.slug}): ${a.desc}`).join("\n") + `

## サイト情報 / Site Information
- **URL**: https://ghost.voronoi.works/
- **Sitemap**: https://ghost.voronoi.works/sitemap.xml
- **著者 / 観測体**: Voronoi Works (隊長, ユラ, スミ, ナギ, シオリ)
`;

fs.writeFileSync("./content/llms.txt", llmsContent, "utf8");
console.log("Successfully updated content/llms.txt with " + articles.length + " articles.");
