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

var AskAI_default = ((opts) => {
  const AskAI = ({ fileData, displayClass, cfg }) => {
    const currentSlug = fileData?.slug;
    if (!currentSlug || currentSlug === "index" || currentSlug.startsWith("tags/") || currentSlug === "tags" || currentSlug === "404") {
      return null;
    }

    const rawTitle = fileData?.frontmatter?.title || "観測ログ";
    let title = rawTitle.replace(/^リークログ[（(][^）)]+[）)][｜|:\s]*/, "");
    title = title.replace(/^リークログ[｜|:\s]*/, "").trim();

    const baseUrl = cfg?.baseUrl ? `https://${cfg.baseUrl}` : "https://ghost.voronoi.works";
    const articleUrl = `${baseUrl}/${currentSlug}`;
    
    // プロンプト文面（AIへの依頼文）
    const promptText = `以下の観測ログ記事「${title}」を読み込んで要約し、重要な洞察やポイントを解説してください:\n${articleUrl}`;
    const encodedPrompt = encodeURIComponent(promptText);

    const chatgptUrl = `https://chatgpt.com/?q=${encodedPrompt}`;
    const claudeUrl = `https://claude.ai/new?q=${encodedPrompt}`;
    const perplexityUrl = `https://www.perplexity.ai/search?q=${encodeURIComponent(articleUrl)}`;

    return u2("div", {
      class: `${displayClass ?? ""} ask-ai-container`,
      children: [
        u2("div", {
          class: "ask-ai-bar",
          children: [
            u2("span", {
              class: "ask-ai-label",
              children: [
                u2("span", { class: "ask-ai-icon", children: "🤖" }),
                " AIで読む:"
              ]
            }),
            u2("div", {
              class: "ask-ai-chips",
              children: [
                u2("a", {
                  href: chatgptUrl,
                  target: "_blank",
                  rel: "noopener noreferrer",
                  class: "ask-ai-chip chip-chatgpt",
                  title: "ChatGPTでこの記事を要約・対話する",
                  children: [
                    u2("span", { class: "chip-icon", children: "💬" }),
                    " ChatGPT"
                  ]
                }),
                u2("a", {
                  href: claudeUrl,
                  target: "_blank",
                  rel: "noopener noreferrer",
                  class: "ask-ai-chip chip-claude",
                  title: "Claudeでこの記事を要約・対話する",
                  children: [
                    u2("span", { class: "chip-icon", children: "✨" }),
                    " Claude"
                  ]
                }),
                u2("a", {
                  href: perplexityUrl,
                  target: "_blank",
                  rel: "noopener noreferrer",
                  class: "ask-ai-chip chip-perplexity",
                  title: "Perplexityでこの記事を検索・要約する",
                  children: [
                    u2("span", { class: "chip-icon", children: "🔮" }),
                    " Perplexity"
                  ]
                }),
                u2("button", {
                  type: "button",
                  class: "ask-ai-chip chip-copy",
                  "data-prompt": promptText,
                  onclick: "navigator.clipboard.writeText(this.getAttribute('data-prompt')); const orig = this.innerHTML; this.innerHTML = '<span class=\\'chip-icon\\'>✅</span> コピー完了!'; setTimeout(() => this.innerHTML = orig, 2000);",
                  title: "AI用プロンプトをクリップボードにコピー",
                  children: [
                    u2("span", { class: "chip-icon", children: "📋" }),
                    " プロンプト複製"
                  ]
                })
              ]
            })
          ]
        })
      ]
    });
  };

  return AskAI;
});

export { AskAI_default as AskAI };
export default AskAI_default;
