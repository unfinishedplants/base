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
  filter: (f: { slug?: string; frontmatter?: { created?: unknown } }) =>
    !!f.slug?.startsWith("opl｜ログdb/") && !!f.frontmatter?.created,
})

// 右サイドバー（Graph View/最近の観測ログ/TOC）はposition:stickyでheight:100vh・
// overflow:hiddenにしてある（quartz/styles/base.scss）。中身の合計が100vhを
// 超える場合、スクロール量に応じてtranslateYで中身を少しずつ上へスライドさせ、
// はみ出した下の方（TOCの後半など）も内部スクロールバー無しで読めるようにする。
// 記事の終わり付近ではsticky自体が解除されて通常通り上へ流れて消えていく。
//
// afterDOMLoadedは「登録済みコンポーネントのコンストラクタ関数」ではなく、
// そのコンストラクタを呼び出した「戻り値（実際にレンダリングされる側）」に
// 付いている必要がある（componentRegistry.getAllComponents()が読むのは
// instantiate()の戻り値）。既存コンポーネントを間借りするのではなく、
// 何も描画しない専用のダミーコンポーネントをローカル登録し、その戻り値に
// スクリプトを付けることで確実に配信されるようにする。
const stickyRevealScript = `
(function () {
  if (window.__quartzStickyRevealCleanup) {
    window.__quartzStickyRevealCleanup()
  }
  var sidebar = document.querySelector(".sidebar.right")
  if (!sidebar) return
  var mq = window.matchMedia("(min-width: 1200px)")
  var maxTranslate = 0
  var resizeTimeout

  function recalc() {
    if (!mq.matches) {
      sidebar.style.transform = ""
      return
    }
    sidebar.style.transform = ""
    var contentH = sidebar.scrollHeight
    maxTranslate = Math.max(0, contentH - window.innerHeight)
    onScroll()
  }

  function debouncedRecalc() {
    if (!mq.matches) {
      sidebar.style.transform = ""
      clearTimeout(resizeTimeout)
      return
    }
    clearTimeout(resizeTimeout)
    resizeTimeout = setTimeout(recalc, 150)
  }

  function onScroll() {
    if (!mq.matches || maxTranslate <= 0) {
      sidebar.style.transform = ""
      return
    }
    var pageScrollMax = document.documentElement.scrollHeight - window.innerHeight
    if (pageScrollMax <= 0) {
      sidebar.style.transform = ""
      return
    }
    // ページ全体のスクロール進捗率 (0.0 〜 1.0) に応じて、滑らかにスライド量を補間
    var ratio = window.scrollY / pageScrollMax
    var translate = ratio * maxTranslate
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
  window.addEventListener("resize", debouncedRecalc)
  window.__quartzStickyRevealCleanup = function () {
    window.removeEventListener("scroll", scheduleScroll)
    window.removeEventListener("resize", debouncedRecalc)
    clearTimeout(resizeTimeout)
    sidebar.style.transform = ""
  }
  recalc()
})()
`

const StickyRevealScript: QuartzComponentConstructor = () => {
  const Component = (() => null) as QuartzComponent
  Component.afterDOMLoaded = stickyRevealScript
  return Component
}
componentRegistry.register("sticky-reveal-script", StickyRevealScript, "local")

const config = await loadQuartzConfig()
export default config
export const layout = await loadQuartzLayout()
