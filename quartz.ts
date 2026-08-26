import { loadQuartzConfig, loadQuartzLayout } from "./quartz/plugins/loader/config-loader"
import { componentRegistry } from "./quartz/components/registry"
import type { QuartzComponent, QuartzComponentConstructor } from "./quartz/components/types"

// 「最近の観測ログ」(recent-notes, 右サイドバー) をOPL｜ログDB配下・かつ
// 観測日/導入日由来の`created`日付を持つノートだけに絞る。
// hideFolderPages はYAML側options（quartz.config.yaml）で設定済み。
componentRegistry.setOptionOverrides("recent-notes", {
  filter: (f: { slug?: string; frontmatter?: { date?: unknown; created?: unknown } }) =>
    f.slug !== "index" && (!!f.frontmatter?.date || !!f.frontmatter?.created),
})

// 「観測ログ一覧」(explorer, 左サイドバー) のタイトル短縮・クレンジング・日付降順ソート
// 1. mapFn: 「リークログ｜」接頭辞を削除し、副題を整理して「MM/DD コアタイトル」にスリム化
// 2. sortFn: 日付（YYYY-MM-DD）の新しい順（降順）にソート
// 3. filterFn: tags/index などを除外
componentRegistry.setOptionOverrides("explorer", {
  title: "📂 観測ログ一覧",
  mapFn: (node: any) => {
    if (node.isFolder) return node
    const rawTitle = node.data?.title || node.displayName || ""
    if (rawTitle === "index") return node

    // 1. 定型プレフィックスの除去
    let title = rawTitle.replace(/^リークログ[（(][^）)]+[）)][｜|:\s]*/, "")
    title = title.replace(/^リークログ[｜|:\s]*/, "")

    // 2. 「――」「——」などの副題区切りがある場合、長すぎたらカットしてすっきりさせる
    if (title.length > 20 && (title.includes("――") || title.includes("——") || title.includes("―") || title.includes(" - "))) {
      title = title.split(/[―—]{1,2}| - /)[0].trim()
    }

    // 3. slug (YYYY-MM-DD-xxx) から MM/DD を抽出して付与
    const slug = node.data?.slug || ""
    const dateMatch = slug.match(/(\d{4})-(\d{2})-(\d{2})/)
    let datePrefix = ""
    if (dateMatch) {
      datePrefix = dateMatch[2] + "/" + dateMatch[3] + " "
    }

    if (title) {
      node.displayName = (datePrefix + title).trim()
    }
    return node
  },
  sortFn: (a: any, b: any) => {
    if ((!a.isFolder && !b.isFolder) || (a.isFolder && b.isFolder)) {
      const slugA = a.data?.slug || a.slugSegment || ""
      const slugB = b.data?.slug || b.slugSegment || ""
      const dateA = slugA.match(/^(\d{4}-\d{2}-\d{2})/)
      const dateB = slugB.match(/^(\d{4}-\d{2}-\d{2})/)

      if (dateA && dateB) {
        return dateB[1].localeCompare(dateA[1])
      }
      if (dateA && !dateB) return -1
      if (!dateA && dateB) return 1

      return (a.displayName || "").localeCompare(b.displayName || "", undefined, {
        numeric: true,
        sensitivity: "base",
      })
    }
    if (!a.isFolder && b.isFolder) return 1
    return -1
  },
  filterFn: (node: any) => {
    if (node.slugSegment === "tags" || node.slugSegment === "private" || node.slugSegment === "templates") {
      return false
    }
    if (node.slugSegment === "index" || node.data?.slug === "index") {
      return false
    }
    return true
  },
  order: ["filter", "map", "sort"],
})



const config = await loadQuartzConfig()
export default config
export const layout = await loadQuartzLayout()
