import { loadQuartzConfig, loadQuartzLayout } from "./quartz/plugins/loader/config-loader"
import { componentRegistry } from "./quartz/components/registry"
import type { QuartzComponent, QuartzComponentConstructor } from "./quartz/components/types"

// 「最近の観測ログ」(recent-notes, 右サイドバー) をOPL｜ログDB配下・かつ
// 観測日/導入日由来の`created`日付を持つノートだけに絞る。
// hideFolderPages はYAML側options（quartz.config.yaml）で設定済み。
// filterはYAML(関数値をシリアライズできない)では表現できないため、
// componentRegistryのTSオーバーライド経路（config-loader.tsがYAMLのoptionsとマージする）で注入する。
// このコンポーネントはSSR時にフル情報のQuartzPluginDataを使うため
// （Explorerサイドバーと違い、日付がcontentIndex.jsonで欠落する問題はない）。
// 注意: `f.dates.created` はgit/filesystemへのフォールバック後の値なので、
// 観測日/導入日を持たないノートでも常にtruthyになってしまう。
// 実際に観測日/導入日由来のcreated:が注入されたノートかどうかは、
// フォールバック前の生フロントマター `f.frontmatter.created` の有無で判定する。
componentRegistry.setOptionOverrides("recent-notes", {
  filter: (f: { slug?: string; frontmatter?: { date?: unknown; created?: unknown } }) =>
    f.slug !== "index" && (!!f.frontmatter?.date || !!f.frontmatter?.created),
})



const config = await loadQuartzConfig()
export default config
export const layout = await loadQuartzLayout()
