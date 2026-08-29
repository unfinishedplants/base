import fs from "fs"
import path from "path"
import YAML from "yaml"

const publicDir = "./public"

console.log("=== Running OPL Quartz Build & SEO/Feed Verification ===")

let failures = []
function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message)
    failures.push(message)
  } else {
    console.log("PASS: " + message)
  }
}

// 0. Check tracked custom-plugins and quartz.config.yaml sources
assert(
  fs.existsSync("./custom-plugins/description-cleaner.js"),
  "custom-plugins/description-cleaner.js exists (shared description cleaner)",
)
assert(
  fs.existsSync("./custom-plugins/created-modified-date/package.json"),
  "custom-plugins/created-modified-date/package.json exists",
)
assert(
  fs.existsSync("./custom-plugins/created-modified-date/dist/index.js"),
  "custom-plugins/created-modified-date/dist/index.js exists",
)
assert(
  fs.existsSync("./custom-plugins/description/package.json"),
  "custom-plugins/description/package.json exists",
)
assert(
  fs.existsSync("./custom-plugins/description/dist/index.js"),
  "custom-plugins/description/dist/index.js exists",
)
assert(
  fs.existsSync("./custom-plugins/content-index/package.json"),
  "custom-plugins/content-index/package.json exists",
)
assert(
  fs.existsSync("./custom-plugins/content-index/dist/index.js"),
  "custom-plugins/content-index/dist/index.js exists",
)

const configContent = fs.readFileSync("./quartz.config.yaml", "utf8")
const config = YAML.parse(configContent)
const pluginSources = (config.plugins || []).map((p) => p?.source)

assert(
  pluginSources.includes("./custom-plugins/created-modified-date"),
  "quartz.config.yaml uses ./custom-plugins/created-modified-date",
)
assert(
  pluginSources.includes("./custom-plugins/description"),
  "quartz.config.yaml uses ./custom-plugins/description",
)
assert(
  pluginSources.includes("./custom-plugins/content-index"),
  "quartz.config.yaml uses ./custom-plugins/content-index",
)

// 1. Check index.xml (RSS Feed)
const rssPath = path.join(publicDir, "index.xml")
assert(fs.existsSync(rssPath), "index.xml exists")
if (fs.existsSync(rssPath)) {
  const rss = fs.readFileSync(rssPath, "utf8")
  assert(rss.includes('<rss version="2.0">'), "RSS version 2.0 header present")
  assert(
    rss.includes("<link>https://ghost.voronoi.works/</link>"),
    "RSS channel link is https://ghost.voronoi.works/",
  )

  const itemMatches = [...rss.matchAll(/<item>([\s\S]*?)<\/item>/g)]
  assert(itemMatches.length > 0, `RSS contains ${itemMatches.length} items`)

  // Verify that NO items are tag pages or index or 404
  let tagCount = 0
  let invalidDescCount = 0
  let itemsParsed = []

  for (const m of itemMatches) {
    const item = m[1]
    const titleMatch = item.match(/<title>(.*?)<\/title>/)
    const linkMatch = item.match(/<link>(.*?)<\/link>/)
    const descMatch = item.match(/<description><!\[CDATA\[([\s\S]*?)\]\]><\/description>/)
    const pubDateMatch = item.match(/<pubDate>(.*?)<\/pubDate>/)

    const title = titleMatch ? titleMatch[1] : ""
    const link = linkMatch ? linkMatch[1] : ""
    const desc = descMatch ? descMatch[1].trim() : ""
    const pubDate = pubDateMatch ? pubDateMatch[1] : ""

    if (
      link.includes("/tags/") ||
      link.endsWith("/tags") ||
      link.endsWith("/index") ||
      link.endsWith("/404")
    ) {
      tagCount++
    }
    if (!desc || desc.length === 0) {
      invalidDescCount++
    }
    itemsParsed.push({ title, link, desc, pubDate })
  }

  assert(tagCount === 0, "No tag pages or 404/index found in RSS feed items")
  assert(invalidDescCount === 0, "All RSS feed items have non-empty descriptions")

  // Verify the feed remains newest-first without hard-coding a specific article.
  if (itemsParsed.length > 0) {
    console.log("RSS First item:", itemsParsed[0].title, "->", itemsParsed[0].link, "pubDate:", itemsParsed[0].pubDate)
    const pubDates = itemsParsed.map((item) => Date.parse(item.pubDate))
    const firstPubDate = pubDates[0]
    const newestPubDate = Math.max(...pubDates)
    console.log("All pubDates:", itemsParsed.map(i => `${i.title.slice(0, 15)}: ${i.pubDate}`))
    console.log("firstPubDate:", firstPubDate, "newestPubDate:", newestPubDate)
    assert(
      pubDates.every(Number.isFinite) && firstPubDate >= newestPubDate,
      "RSS first item is the newest article",
    )
  }
}

// 2. Check sitemap.xml
const sitemapPath = path.join(publicDir, "sitemap.xml")
assert(fs.existsSync(sitemapPath), "sitemap.xml exists")
if (fs.existsSync(sitemapPath)) {
  const sitemap = fs.readFileSync(sitemapPath, "utf8")
  assert(
    sitemap.includes("<loc>https://ghost.voronoi.works/</loc>"),
    "Sitemap includes root https://ghost.voronoi.works/",
  )

  // Verify tag pages do not have lastmod
  const tagUrlMatches = [
    ...sitemap.matchAll(
      /<url>\s*<loc>(https:\/\/ghost\.voronoi\.works\/tags\/[^<]+)<\/loc>([\s\S]*?)<\/url>/g,
    ),
  ]
  let tagWithLastmod = 0
  for (const m of tagUrlMatches) {
    if (m[2].includes("<lastmod>")) {
      tagWithLastmod++
    }
  }
  assert(
    tagWithLastmod === 0,
    `Tag pages have no fake build-time lastmod (${tagUrlMatches.length} tag URLs checked)`,
  )
}

// 3. Check public/index.html
const indexHtmlPath = path.join(publicDir, "index.html")
assert(fs.existsSync(indexHtmlPath), "index.html exists")
if (fs.existsSync(indexHtmlPath)) {
  const html = fs.readFileSync(indexHtmlPath, "utf8")
  assert(html.includes('<html lang="ja"'), 'index.html has lang="ja"')
  assert(
    html.includes('<link rel="canonical" href="https://ghost.voronoi.works/"/>') ||
      html.includes('<link rel="canonical" href="https://ghost.voronoi.works/" />'),
    'index.html has canonical href="https://ghost.voronoi.works/"',
  )
  assert(
    html.includes('<meta property="og:type" content="website"/>') ||
      html.includes('<meta property="og:type" content="website" />'),
    'index.html has og:type="website"',
  )
  assert(
    html.includes('<meta property="og:url" content="https://ghost.voronoi.works/"/>') ||
      html.includes('<meta property="og:url" content="https://ghost.voronoi.works/" />'),
    'index.html has og:url="https://ghost.voronoi.works/"',
  )
}

// 4. Check articles HTML
const testArticles = [
  "2026-08-26-micro-2026-08-26-nagi-name-only-sprint.html",
  "2026-08-18-human-harness-and-digital-iwakura.html",
  "2026-07-04-spaghetti.html",
  "2026-07-08-yura-bokukko-bug.html",
]

for (const art of testArticles) {
  const artPath = path.join(publicDir, art)
  assert(fs.existsSync(artPath), `${art} exists`)
  if (fs.existsSync(artPath)) {
    const html = fs.readFileSync(artPath, "utf8")
    const slug = art.replace(/\.html$/, "")
    const expectedCanonical = `https://ghost.voronoi.works/${slug}`

    assert(html.includes('<html lang="ja"'), `${art} has lang="ja"`)
    assert(
      html.includes(`canonical" href="${expectedCanonical}"`),
      `${art} has exact canonical URL ${expectedCanonical}`,
    )
    assert(html.includes('og:type" content="article"'), `${art} has og:type="article"`)

    // Check JSON-LD
    const jsonLdMatch = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)
    assert(Boolean(jsonLdMatch), `${art} has JSON-LD script`)
    if (jsonLdMatch) {
      try {
        const parsed = JSON.parse(jsonLdMatch[1])
        assert(
          parsed["@type"] === "BlogPosting" || parsed["@type"] === "Article",
          `${art} JSON-LD @type is BlogPosting/Article`,
        )
        assert(parsed.url === expectedCanonical, `${art} JSON-LD url matches canonical`)
        assert(Boolean(parsed.headline), `${art} JSON-LD has headline`)
        assert(Boolean(parsed.description), `${art} JSON-LD has description`)
        assert(
          Boolean(parsed.author && parsed.author.name),
          `${art} JSON-LD has author (${parsed.author?.name})`,
        )
        assert(
          Boolean(parsed.publisher && parsed.publisher.name),
          `${art} JSON-LD has publisher (${parsed.publisher?.name})`,
        )
      } catch (e) {
        assert(false, `${art} JSON-LD is valid JSON: ${e.message}`)
      }
    }
  }
}

// 5. Check llms.txt
const llmsPath = path.join(publicDir, "llms.txt")
assert(fs.existsSync(llmsPath), "public/llms.txt exists")
if (fs.existsSync(llmsPath)) {
  const llms = fs.readFileSync(llmsPath, "utf8")
  const articleFiles = fs
    .readdirSync("./content")
    .filter((file) => file.endsWith(".md") && file !== "index.md")

  assert(!llms.includes("未検出画像"), "llms.txt has no '未検出画像'")
  assert(!llms.includes("![PXL"), "llms.txt has no raw '![PXL' image tags")
  assert(
    !llms.includes("ひぎィィィッ！！！:"),
    "llms.txt has no exclamation placeholder descriptions",
  )
  assert(
    llms.includes(`Observation Logs (${articleFiles.length} articles)`),
    `llms.txt reports the current article count (${articleFiles.length})`,
  )

  for (const file of articleFiles) {
    const source = fs.readFileSync(path.join("./content", file), "utf8")
    const frontmatterMatch = source.match(/^---\r?\n([\s\S]*?)\r?\n---/)
    assert(Boolean(frontmatterMatch), `${file} has frontmatter`)
    const frontmatter = frontmatterMatch ? YAML.parse(frontmatterMatch[1]) ?? {} : {}
    const description = String(
      frontmatter.description ?? frontmatter.socialDescription ?? "",
    ).trim()
    const slug = String(frontmatter.slug ?? file.replace(/\.md$/, "")).trim()

    assert(Boolean(description), `${file} has an explicit description`)
    assert(
      !/ひぎィ|ボゴォ/.test(description),
      `${file} description has no opening scream`,
    )
    assert(
      llms.includes(`https://ghost.voronoi.works/${slug}`),
      `llms.txt includes ${slug}`,
    )
    assert(
      llms.includes(description),
      `llms.txt uses the explicit description for ${slug}`,
    )
  }
}

console.log("\n=== Verification Summary ===")
if (failures.length === 0) {
  console.log("ALL CHECKS PASSED SUCCESSFULLY!")
  process.exit(0)
} else {
  console.error(`${failures.length} CHECKS FAILED:`)
  for (const f of failures) console.error(`- ${f}`)
  process.exit(1)
}
