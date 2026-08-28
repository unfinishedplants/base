# SNS 用素材（サイトには公開されない）

X / Instagram へ直接アップロードするティザー画像の置き場。

`content/` の外にあるため Quartz のビルド対象に含まれず、サイトには
デプロイされない。記事本文から参照する画像は `content/attachments/` に置くこと。

将来 OGP カード画像として使う場合（`og-image` プラグイン有効）は、
frontmatter の `socialImage:` から参照できるよう `content/` 配下へ戻す必要がある。
