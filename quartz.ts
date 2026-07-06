import { loadQuartzConfig, loadQuartzLayout } from "./quartz/plugins/loader/config-loader"
import { componentRegistry } from "./quartz/components/registry"
import type { FileTrieNode } from "./quartz/util/fileTrie"

// Explorerサイドバーのソート順をYAML経由では設定できない（sortFnは関数でシリアライズ不可）ため、
// componentRegistryのTSオーバーライド経路（config-loader.tsがYAMLのoptionsとマージする）を使って
// フォルダは従来通りアルファベット順、ファイル同士は`created`日付（観測日/導入日）の新しい順にする。
// `created-modified-date`プラグインがセットする`dates.created`は、クライアント側では
// JSONを経由した文字列になっているため、Dateオブジェクト/ISO文字列どちらでも動くよう
// `new Date(x).getTime()`で統一的に扱う。
const sortByDateThenAlphabetical = (a: FileTrieNode, b: FileTrieNode): number => {
  if (a.isFolder && b.isFolder) {
    return (a.displayName || "").localeCompare(b.displayName || "", undefined, {
      numeric: true,
      sensitivity: "base",
    })
  }
  if (a.isFolder !== b.isFolder) {
    return a.isFolder ? -1 : 1
  }

  const rawA = (a.data as { dates?: { created?: unknown } } | null)?.dates?.created
  const rawB = (b.data as { dates?: { created?: unknown } } | null)?.dates?.created
  const dateA = rawA ? new Date(rawA as string).getTime() : 0
  const dateB = rawB ? new Date(rawB as string).getTime() : 0
  if (dateA !== dateB) return dateB - dateA

  return (a.displayName || "").localeCompare(b.displayName || "", undefined, {
    numeric: true,
    sensitivity: "base",
  })
}

componentRegistry.setOptionOverrides("explorer", {
  sortFn: sortByDateThenAlphabetical,
})

const config = await loadQuartzConfig()
export default config
export const layout = await loadQuartzLayout()
