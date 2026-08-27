import { resolveRelative } from "@quartz-community/utils/path";

// Preact JSX runtime helper
var f2 = 0;
function u2(e2, t2, n2, o2, i2, u3) {
  t2 || (t2 = {});
  var a2, c2, p2 = t2;
  if ("ref" in p2) for (c2 in p2 = {}, t2) "ref" == c2 ? a2 = t2[c2] : p2[c2] = t2[c2];
  var l2 = { type: e2, props: p2, key: n2, ref: a2, __k: null, __: null, __b: 0, __e: null, __c: null, constructor: void 0, __v: --f2, __i: -1, __u: 0, __source: i2, __self: u3 };
  if ("function" == typeof e2 && (a2 = e2.defaultProps)) for (c2 in a2) void 0 === p2[c2] && (p2[c2] = a2[c2]);
  return l2;
}

function cleanTitle(rawTitle) {
  if (!rawTitle) return "";
  let title = rawTitle.replace(/^リークログ[（(][^）)]+[）)][｜|:\s]*/, "");
  title = title.replace(/^リークログ[｜|:\s]*/, "");
  if (title.length > 28 && (title.includes("――") || title.includes("——") || title.includes("―") || title.includes(" - "))) {
    title = title.split(/[―—]{1,2}| - /)[0].trim();
  }
  return title.trim() || rawTitle;
}

function formatDate(slug, frontmatterDate) {
  if (typeof frontmatterDate === "string") {
    const m = frontmatterDate.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (m) return `${m[2]}/${m[3]}`;
  }
  if (slug) {
    const slugMatch = slug.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (slugMatch) return `${slugMatch[2]}/${slugMatch[3]}`;
  }
  return "";
}

var PrevNext_default = ((opts) => {
  const PrevNext = ({ fileData, allFiles, displayClass }) => {
    const currentSlug = fileData?.slug;
    if (!currentSlug || currentSlug === "index" || currentSlug.startsWith("tags/") || currentSlug === "tags" || currentSlug === "404") {
      return null;
    }

    // 1. 全記事を収集・フィルタリング
    const articles = (allFiles || []).filter((f) => {
      const slug = f?.slug || "";
      if (!slug || slug === "index" || slug.startsWith("tags/") || slug === "tags" || slug === "404") {
        return false;
      }
      if (slug.startsWith("private/") || slug.startsWith("templates/")) {
        return false;
      }
      return true;
    });

    // 2. 日付順（古い順：昇順）にソートして時系列ラインを形成
    articles.sort((a, b) => {
      const slugA = a?.slug || "";
      const slugB = b?.slug || "";
      const dateA = slugA.match(/^(\d{4}-\d{2}-\d{2})/);
      const dateB = slugB.match(/^(\d{4}-\d{2}-\d{2})/);
      if (dateA && dateB) {
        return dateA[1].localeCompare(dateB[1]);
      }
      if (dateA && !dateB) return 1;
      if (!dateA && dateB) return -1;
      return (a?.frontmatter?.title || slugA).localeCompare(b?.frontmatter?.title || slugB);
    });

    // 3. 現在の記事のインデックスを特定
    const currentIndex = articles.findIndex((f) => f?.slug === currentSlug);
    if (currentIndex === -1) {
      return null;
    }

    // 4. 前の記事（Older: index - 1）と 次の記事（Newer: index + 1）を取得
    const prevArticle = currentIndex > 0 ? articles[currentIndex - 1] : null;
    const nextArticle = currentIndex < articles.length - 1 ? articles[currentIndex + 1] : null;

    if (!prevArticle && !nextArticle) {
      return null;
    }

    const prevDate = prevArticle ? formatDate(prevArticle.slug, prevArticle.frontmatter?.date) : "";
    const nextDate = nextArticle ? formatDate(nextArticle.slug, nextArticle.frontmatter?.date) : "";

    return u2("nav", {
      class: `${displayClass ?? ""} prev-next-nav`,
      children: [
        u2("div", {
          class: "prev-next-container",
          children: [
            prevArticle
              ? u2("a", {
                  href: resolveRelative(currentSlug, prevArticle.slug),
                  class: "prev-next-card prev-card",
                  children: [
                    u2("span", { class: "card-direction", children: "← 前の観測ログ" }),
                    u2("span", {
                      class: "card-title",
                      children: [
                        prevDate ? u2("span", { class: "card-date", children: prevDate + " " }) : null,
                        cleanTitle(prevArticle.frontmatter?.title || prevArticle.slug)
                      ]
                    })
                  ]
                })
              : u2("div", { class: "prev-next-card empty-card" }),

            nextArticle
              ? u2("a", {
                  href: resolveRelative(currentSlug, nextArticle.slug),
                  class: "prev-next-card next-card",
                  children: [
                    u2("span", { class: "card-direction", children: "次の観測ログ →" }),
                    u2("span", {
                      class: "card-title",
                      children: [
                        nextDate ? u2("span", { class: "card-date", children: nextDate + " " }) : null,
                        cleanTitle(nextArticle.frontmatter?.title || nextArticle.slug)
                      ]
                    })
                  ]
                })
              : u2("div", { class: "prev-next-card empty-card" })
          ]
        })
      ]
    });
  };

  return PrevNext;
});

export { PrevNext_default as PrevNext };
export default PrevNext_default;
