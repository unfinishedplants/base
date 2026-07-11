import { loadQuartzConfig, loadQuartzLayout } from "./quartz/plugins/loader/config-loader"
import { componentRegistry } from "./quartz/components/registry"

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
  filter: (f: { slug?: string; frontmatter?: { created?: unknown } }) =>
    !!f.slug?.startsWith("opl｜ログdb/") && !!f.frontmatter?.created,
})

const config = await loadQuartzConfig()
export default config
export const layout = await loadQuartzLayout()

// 右サイドバー（Graph View/最近の観測ログ/TOC）はposition:stickyでheight:100vh・
// overflow:hiddenにしてある（quartz/styles/base.scss）。中身の合計が100vhを
// 超える場合、スクロール量に応じてtranslateYで中身を少しずつ上へスライドさせ、
// はみ出した下の方（TOCの後半など）も内部スクロールバー無しで読めるようにする。
// 記事の終わり付近ではsticky自体が解除されて通常通り上へ流れて消えていく。
//
// componentRegistryはビルド時のリソース収集（ComponentResources emitter）でも
// 同じインスタンスを参照するため、既存コンポーネント（recent-notes）の
// afterDOMLoadedに追記するだけで、Quartzの標準的な仕組み（初回読み込み・
// SPAナビゲーションの両方で再実行される）に乗って配信される。
const stickyRevealScript = `
(function () {
  if (window.__quartzStickyRevealCleanup) {
    window.__quartzStickyRevealCleanup()
  }
  var sidebar = document.querySelector(".sidebar.right")
  if (!sidebar) return
  var mq = window.matchMedia("(min-width: 1200px)")
  var containerTop = 0
  var maxTranslate = 0

  function recalc() {
    if (!mq.matches) {
      sidebar.style.transform = ""
      return
    }
    sidebar.style.transform = ""
    var rect = sidebar.getBoundingClientRect()
    containerTop = rect.top + window.scrollY
    var contentH = sidebar.scrollHeight
    maxTranslate = Math.max(0, contentH - window.innerHeight)
    onScroll()
  }

  function onScroll() {
    if (!mq.matches || maxTranslate <= 0) {
      sidebar.style.transform = ""
      return
    }
    var scrolledPastStick = window.scrollY - containerTop
    var translate = Math.min(Math.max(scrolledPastStick, 0), maxTranslate)
    sidebar.style.transform = "translateY(-" + translate + "px)"
  }

  var ticking = false
  function scheduleScroll() {
    if (!ticking) {
      ticking = true
      requestAnimationFrame(function () {
        onScroll()
        ticking = false
      })
    }
  }

  window.addEventListener("scroll", scheduleScroll, { passive: true })
  window.addEventListener("resize", recalc)
  window.__quartzStickyRevealCleanup = function () {
    window.removeEventListener("scroll", scheduleScroll)
    window.removeEventListener("resize", recalc)
    sidebar.style.transform = ""
  }
  recalc()
})()
`

const recentNotesReg = componentRegistry.get("recent-notes")
if (recentNotesReg && typeof recentNotesReg.component === "function") {
  const ctor = recentNotesReg.component as unknown as { afterDOMLoaded?: string }
  ctor.afterDOMLoaded = (typeof ctor.afterDOMLoaded === "string" ? ctor.afterDOMLoaded : "") + stickyRevealScript
}
