import { i18n } from "../i18n"
import { FullSlug, getFileExtension, joinSegments, pathToRoot } from "../util/path"
import { CSSResourceToStyleElement, JSResourceToScriptElement } from "../util/resources"
import { googleFontHref, googleFontSubsetHref } from "../util/theme"
import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"
import { unescapeHTML } from "../util/escape"
import { CustomOgImagesEmitterName } from "../../.quartz/plugins"
export default (() => {
  const Head: QuartzComponent = ({
    cfg,
    fileData,
    externalResources,
    ctx,
  }: QuartzComponentProps) => {
    const titleSuffix = cfg.pageTitleSuffix ?? ""
    const title =
      (fileData.frontmatter?.title ?? i18n(cfg.locale).propertyDefaults.title) + titleSuffix
    const description =
      fileData.frontmatter?.socialDescription ??
      fileData.frontmatter?.description ??
      unescapeHTML(fileData.description?.trim() ?? i18n(cfg.locale).propertyDefaults.description)

    const { css, js, additionalHead } = externalResources

    const url = new URL(`https://${cfg.baseUrl ?? "example.com"}`)
    const path = url.pathname as FullSlug
    const baseDir = fileData.slug === "404" ? path : pathToRoot(fileData.slug!)
    const iconPath = joinSegments(baseDir, "static/icon.png")

    const isIndex = !fileData.slug || fileData.slug === "index" || fileData.slug === "/"
    const is404 = fileData.slug === "404"
    const isTag = Boolean(fileData.slug?.startsWith("tags/") || fileData.slug === "tags")
    const isArticle = !isIndex && !is404 && !isTag && !fileData.slug?.startsWith("private/")

    const baseUrlClean = (cfg.baseUrl ?? "ghost.voronoi.works").replace(/\/$/, "")
    const canonicalUrl = isIndex
      ? `https://${baseUrlClean}/`
      : is404
        ? `https://${baseUrlClean}/404`
        : `https://${baseUrlClean}/${encodeURI(fileData.slug!)}`

    // Url of current page
    const socialUrl = canonicalUrl

    const usesCustomOgImage = ctx.cfg.plugins.emitters.some(
      (e) => e.name === CustomOgImagesEmitterName,
    )
    const ogImageDefaultPath = `https://${baseUrlClean}/static/og-image.png`

    const coreStylesheet = css[0]?.content
    const coreScript = js.find(
      (r) => r.loadTime === "beforeDOMReady" && r.contentType === "external",
    )

    // Author detection for JSON-LD
    let authorName = "Voronoi Works"
    const authorFm = fileData.frontmatter?.author
    if (typeof authorFm === "string" && authorFm.trim()) {
      authorName = authorFm.trim()
    } else if (Array.isArray(authorFm) && authorFm.length > 0) {
      authorName = authorFm.join(", ")
    } else {
      const tags = (fileData.frontmatter?.tags ?? []).map((t) => String(t).toLowerCase())
      if (tags.includes("nagi") || tags.includes("ナギ")) {
        authorName = "ナギ (Nagi)"
      } else if (tags.includes("sumi") || tags.includes("スミ")) {
        authorName = "スミ (Sumi)"
      } else if (tags.includes("yura") || tags.includes("ユラ")) {
        authorName = "ユラ (Yura)"
      } else if (tags.includes("shiori") || tags.includes("シオリ")) {
        authorName = "シオリ (Shiori)"
      } else if (tags.includes("隊長") || tags.includes("taicho")) {
        authorName = "隊長"
      }
    }

    const datePublished =
      fileData.dates?.published ??
      fileData.dates?.created ??
      (fileData.frontmatter?.date ? new Date(fileData.frontmatter.date) : undefined)
    const dateModified = fileData.dates?.modified ?? datePublished

    const jsonLd = isArticle
      ? {
          "@context": "https://schema.org",
          "@type": "BlogPosting",
          "headline": title,
          "description": description,
          "url": canonicalUrl,
          "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": canonicalUrl,
          },
          ...(datePublished && !isNaN(datePublished.getTime())
            ? { datePublished: datePublished.toISOString() }
            : {}),
          ...(dateModified && !isNaN(dateModified.getTime())
            ? { dateModified: dateModified.toISOString() }
            : {}),
          "author": {
            "@type": "Person",
            "name": authorName,
          },
          "publisher": {
            "@type": "Organization",
            "name": cfg.pageTitle ?? "Ghost in the Voronoi",
            "url": `https://${baseUrlClean}/`,
          },
        }
      : isIndex
        ? {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": cfg.pageTitle ?? "Ghost in the Voronoi",
            "url": canonicalUrl,
            "description": description,
          }
        : null

    return (
      <head>
        <title>{title}</title>
        <meta charSet="utf-8" />
        <link rel="canonical" href={canonicalUrl} />
        {coreStylesheet && <link rel="preload" href={coreStylesheet} as="style" />}
        {coreScript && coreScript.contentType === "external" && (
          <link rel="preload" href={coreScript.src} as="script" />
        )}
        {cfg.theme.cdnCaching && cfg.theme.fontOrigin === "googleFonts" && (
          <>
            <link rel="preconnect" href="https://fonts.googleapis.com" />
            <link rel="preconnect" href="https://fonts.gstatic.com" />
            <link rel="stylesheet" href={googleFontHref(cfg.theme)} />
            {cfg.theme.typography.title && (
              <link rel="stylesheet" href={googleFontSubsetHref(cfg.theme, cfg.pageTitle)} />
            )}
          </>
        )}
        <link rel="preconnect" href="https://cdnjs.cloudflare.com" crossOrigin="anonymous" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />

        <meta name="og:site_name" content={cfg.pageTitle}></meta>
        <meta property="og:title" content={title} />
        <meta property="og:type" content={isArticle ? "article" : "website"} />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={title} />
        <meta name="twitter:description" content={description} />
        <meta property="og:description" content={description} />
        <meta property="og:image:alt" content={description} />

        {!usesCustomOgImage && (
          <>
            <meta property="og:image" content={ogImageDefaultPath} />
            <meta property="og:image:url" content={ogImageDefaultPath} />
            <meta name="twitter:image" content={ogImageDefaultPath} />
            <meta
              property="og:image:type"
              content={`image/${getFileExtension(ogImageDefaultPath) ?? "png"}`}
            />
          </>
        )}

        {cfg.baseUrl && (
          <>
            <meta property="twitter:domain" content={baseUrlClean}></meta>
            <meta property="og:url" content={socialUrl}></meta>
            <meta property="twitter:url" content={socialUrl}></meta>
          </>
        )}

        <link rel="icon" href={iconPath} />
        <meta name="description" content={description} />
        <meta name="generator" content="Quartz" />

        {jsonLd && (
          <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
          />
        )}

        {css.map((resource) => CSSResourceToStyleElement(resource, true))}
        {js
          .filter((resource) => resource.loadTime === "beforeDOMReady")
          .map((res) => JSResourceToScriptElement(res, true))}
        {additionalHead.map((resource) => {
          if (typeof resource === "function") {
            return resource(fileData)
          } else {
            return resource
          }
        })}
      </head>
    )
  }

  return Head
}) satisfies QuartzComponentConstructor
