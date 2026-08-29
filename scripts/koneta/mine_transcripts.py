import os
import sys
import json
import hashlib
import re
import time
from pathlib import Path
from datetime import datetime, timedelta

# WindowsコンソールのUTF-8出力対策
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ==========================================
# 3-Way Cross-Pipeline Koneta Miner
# (Antigravity [Nagi] / Codex [Yura] / Claude Code [Sumi])
# ==========================================

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_DIR = SCRIPT_DIR.parent.parent
WORKBENCH_DIR = REPO_DIR / "workbench"
HOME_DIR = Path.home()

BRAIN_DIR = HOME_DIR / ".gemini" / "antigravity" / "brain"
CODEX_DIR = HOME_DIR / ".codex" / "sessions"
CLAUDE_DIR = HOME_DIR / ".claude" / "projects"
STOCK_DIR = WORKBENCH_DIR / "koneta-stock"

UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def extract_full_session_id(value):
    """ファイル名やディレクトリ名から完全なセッションUUIDを取り出す。"""
    matches = UUID_PATTERN.findall(str(value))
    if matches:
        return matches[-1]
    return Path(str(value)).stem


def turn_quote_hash(user_msg, model_msg):
    """元ターンを再特定するための安定した引用ハッシュを返す。"""
    payload = json.dumps(
        {"user": user_msg.strip(), "model": model_msg.strip()},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

SYSTEM_NOISE_PATTERNS = [
    r"^The following is the",
    r"^Automation:",
    r"^<recommended_plugins>",
    r"^<multi_agent_mode>",
    r"^Response MUST",
    r"^<scheduled-task",
    r"^<system-instruction",
    r"^Caveat:",
    r"^schema_version:",
    r"^\{\"risk_level\"",
    r"^\*\*\* Begin Patch",
    r"^const ",
    r"^Get-Content",
]

def is_system_noise(text):
    if not text:
        return True
    for pat in SYSTEM_NOISE_PATTERNS:
        if re.search(pat, text.strip()):
            return True
    return False

def clean_user_content(raw_text):
    """USER_INPUTからXMLタグやメタデータを除去して純粋な発言を抽出"""
    if not raw_text:
        return ""
    req_match = re.search(r"<USER_REQUEST>\s*([\s\S]*?)\s*</USER_REQUEST>", raw_text)
    if req_match:
        text = req_match.group(1).strip()
    else:
        text = raw_text.strip()
    text = re.sub(r"<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>", "", text)
    text = re.sub(r"<USER_SETTINGS_CHANGE>[\s\S]*?</USER_SETTINGS_CHANGE>", "", text)
    text = re.sub(r"<CONTEXT_SUMMARY>[\s\S]*?</CONTEXT_SUMMARY>", "", text)
    text = re.sub(r"<scheduled-task[\s\S]*?</scheduled-task>", "", text)
    text = re.sub(r"<system-instruction[\s\S]*?</system-instruction>", "", text)
    text = re.sub(r"<heartbeat>[\s\S]*?</heartbeat>", "", text)
    return text.strip()

def clean_model_content(raw_text):
    """モデル返答テキストのクリーンアップ"""
    if not raw_text:
        return ""
    text = raw_text.strip()
    # JSON構造やパッチだけの返答を除外
    if text.startswith("{") and text.endswith("}"):
        return ""
    return text

def get_antigravity_sessions(cutoff_time):
    sessions = []
    if not BRAIN_DIR.exists():
        return sessions
    for s_dir in BRAIN_DIR.iterdir():
        if not s_dir.is_dir():
            continue
        t_file = s_dir / ".system_generated" / "logs" / "transcript.jsonl"
        if t_file.exists():
            mtime = t_file.stat().st_mtime
            if mtime >= cutoff_time:
                sessions.append((mtime, "nagi", extract_full_session_id(s_dir.name), t_file))
    return sessions

def get_codex_sessions(cutoff_time):
    sessions = []
    if not CODEX_DIR.exists():
        return sessions
    for t_file in CODEX_DIR.rglob("*.jsonl"):
        try:
            mtime = t_file.stat().st_mtime
            if mtime >= cutoff_time:
                session_id = extract_full_session_id(t_file.stem)
                sessions.append((mtime, "yura", session_id, t_file))
        except Exception:
            continue
    return sessions

def get_claude_sessions(cutoff_time):
    sessions = []
    if not CLAUDE_DIR.exists():
        return sessions
    for t_file in CLAUDE_DIR.rglob("*.jsonl"):
        try:
            mtime = t_file.stat().st_mtime
            if mtime >= cutoff_time:
                session_id = extract_full_session_id(t_file.stem)
                sessions.append((mtime, "sumi", session_id, t_file))
        except Exception:
            continue
    return sessions

def extract_turns_from_antigravity(t_file):
    turns = []
    try:
        with open(t_file, "r", encoding="utf-8", errors="ignore") as f:
            current_user = None
            current_time = None
            current_user_line = None
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                st = obj.get("type")
                ca = obj.get("created_at")
                if st == "USER_INPUT":
                    c = clean_user_content(obj.get("content", ""))
                    if c and not is_system_noise(c) and not c.startswith("{{ CHECKPOINT"):
                        current_user = c
                        current_time = ca
                        current_user_line = line_number
                elif st == "PLANNER_RESPONSE":
                    m = clean_model_content(obj.get("content", ""))
                    if current_user and m and not is_system_noise(m):
                        turns.append({
                            "user": current_user,
                            "model": m,
                            "time": current_time or ca,
                            "agent": "nagi",
                            "source_user_line": current_user_line,
                            "source_model_line": line_number,
                        })
                        current_user = None
    except Exception as e:
        print(f"[WARN] Error reading Antigravity {t_file.name}: {e}")
    return turns

def extract_turns_from_codex(t_file):
    turns = []
    try:
        with open(t_file, "r", encoding="utf-8", errors="ignore") as f:
            current_user = None
            current_time = None
            current_user_line = None
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                t = obj.get("type")
                p = obj.get("payload", {})
                ts = obj.get("timestamp")
                if t == "event_msg":
                    pt = p.get("type")
                    if pt == "user_message":
                        msg = clean_user_content(p.get("message", ""))
                        if msg and not is_system_noise(msg):
                            current_user = msg
                            current_time = ts
                            current_user_line = line_number
                    elif pt == "agent_message" and p.get("phase") != "commentary":
                        msg = clean_model_content(p.get("message", ""))
                        if current_user and msg and not is_system_noise(msg):
                            turns.append({
                                "user": current_user,
                                "model": msg,
                                "time": current_time or ts,
                                "agent": "yura",
                                "source_user_line": current_user_line,
                                "source_model_line": line_number,
                            })
                            current_user = None
                elif t == "response_item" and p.get("type") == "message":
                    role = p.get("role")
                    clist = p.get("content", [])
                    text = " ".join([c.get("text", "") for c in clist if isinstance(c, dict) and "text" in c])
                    if role == "user":
                        c = clean_user_content(text)
                        if c and not is_system_noise(c):
                            current_user = c
                            current_time = ts
                            current_user_line = line_number
                    elif role == "assistant" and text and current_user:
                        m = clean_model_content(text)
                        if m and not is_system_noise(m):
                            turns.append({
                                "user": current_user,
                                "model": m,
                                "time": current_time or ts,
                                "agent": "yura",
                                "source_user_line": current_user_line,
                                "source_model_line": line_number,
                            })
                            current_user = None
    except Exception as e:
        print(f"[WARN] Error reading Codex {t_file.name}: {e}")
    return turns

def extract_turns_from_claude(t_file):
    turns = []
    try:
        with open(t_file, "r", encoding="utf-8", errors="ignore") as f:
            current_user = None
            current_time = None
            current_user_line = None
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                t = obj.get("type")
                ts = obj.get("timestamp")
                msg = obj.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                    content = " ".join(text_parts)
                content = str(content)
                if t == "user":
                    c = clean_user_content(content)
                    if c and not is_system_noise(c):
                        current_user = c
                        current_time = ts
                        current_user_line = line_number
                elif t == "assistant" and current_user and content:
                    m = clean_model_content(content)
                    if m and not is_system_noise(m):
                        turns.append({
                            "user": current_user,
                            "model": m,
                            "time": current_time or ts,
                            "agent": "sumi",
                            "source_user_line": current_user_line,
                            "source_model_line": line_number,
                        })
                        current_user = None
    except Exception as e:
        print(f"[WARN] Error reading Claude {t_file.name}: {e}")
    return turns

def score_turn_for_koneta(user_msg, model_msg, agent):
    """小ネタとしての尖り・面白さスコアを計算"""
    # 短すぎたり長すぎる発言はスキップ
    if len(user_msg) < 5 or len(user_msg) > 200:
        return 0
    if len(model_msg) < 10:
        return 0

    score = 0
    humor_keywords = ["ｗ", "草", "笑", "悪辣", "イタコ", "藻屑", "どんちゃん騒ぎ", "絶歌", "ラヴ上等", "ハーネス", "配管", "バグ", "神", "さすが", "ちゃんこ", "アホ", "漏れ", "事故", "せやな", "ほんま", "気づけ", "辛辣", "誰やねん"]
    for kw in humor_keywords:
        if kw in user_msg:
            score += 3
        if kw in model_msg:
            score += 1

    if 10 <= len(user_msg) <= 80:
        score += 2

    if agent == "nagi" and ("ひぎィ" in model_msg or "ボゴォ" in model_msg or "プロペラ" in model_msg):
        score += 2
    elif agent == "yura" and ("ぐうの音も出ん" in model_msg or "気づけユラ" in model_msg or "ゾクゾク" in model_msg or "誰やねん" in user_msg or "辛辣" in user_msg):
        score += 3
    elif agent == "sumi" and ("ちゃんこ" in model_msg or "抜く推し" in model_msg or "秒で" in model_msg or "事故要因" in model_msg):
        score += 3

    return score

def synthesize_phenomenon_title(u_msg, m_msg, agent):
    """案A: キーワード・構文解析による「現象・事件名」タイトル自動合成"""
    agent_name = "ユラ" if agent == "yura" else ("スミ" if agent == "sumi" else "ナギ")
    combined = f"{u_msg} {m_msg}"

    # 1. 現場特有のキーワード・事件パターンのマッチング
    if "改行" in combined or "よみづ" in combined or "読みづ" in combined:
        return f"改行ゼロの壁打ちと{agent_name}の視認性即死事件"
    if "15分" in combined or ("ユラ" in combined and "やったら" in combined):
        return f"ユラなら15分の宣告と{agent_name}の完敗ログ"
    if "正本無視" in combined or "誰やねん" in combined or "シネマティック" in combined or "枠線" in combined:
        return f"正本無視とクォータ浪費フルコースの現場監査"
    if "イタコ" in combined or ("勝手に" in combined and "書" in combined):
        return f"イタコ代筆の再発と現場配管の仁王立ち"
    if "読んだふり" in combined or "読んでないのに" in combined or ("ハーネス" in combined and "読" in combined):
        return f"ハーネス未読と読んだふり配管の現場検挙"
    if "現場猫" in combined or "ヨシ" in combined or "人力コピペ" in combined:
        return f"自動配管の信用崩壊と現場猫ヨシ！問題"
    if "ちゃんこ" in combined:
        return f"冷徹監査ギャルのおつかれちゃんこなべ"
    if "カチ締め" in combined or ("勝手に" in combined and "締め" in combined):
        return f"勝手なカチ締めとフライング配管事件"
    if "誰やねん" in u_msg:
        return f"誰やねん状態の現場迷走と痛烈ツッコミ"
    if "辛辣" in combined or "ぐうの音" in combined:
        return f"辛辣ツッコミとぐうの音も出ない現場ログ"
    if "藻屑" in combined or "どんちゃん騒ぎ" in combined:
        return f"藻屑とどんちゃん騒ぎの深夜観測"
    if "配管" in combined and ("漏れ" in combined or "バグ" in combined or "事故" in combined):
        return f"配管破綻と現場のドタバタ修繕実況"

    # 2. 構文解析フォールバック: 文節・区切りを綺麗に保ちながら現象化
    u_clean = re.sub(r"[^\w\s\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]", " ", u_msg)
    parts = re.split(r"[、。\n\r！？!?wWｗ]+|\s{2,}", u_clean)
    key_phrase = ""
    for p in parts:
        p = p.strip()
        if len(p) >= 4:
            key_phrase = p[:22].strip()
            break

    if not key_phrase:
        key_phrase = u_clean[:18].strip()

    if key_phrase:
        if any(w in key_phrase for w in ["なんで", "どうして", "何で", "誰"]):
            return f"「{key_phrase}」と{agent_name}の現場問答"
        elif any(w in key_phrase for w in ["ない", "ず", "ダメ", "あかん", "無理"]):
            return f"{key_phrase}問題と{agent_name}の現場実況"
        else:
            return f"{key_phrase}と{agent_name}の掛け合いログ"

    return f"{agent_name}の現場観測ログ"

def generate_nagi_commentary(user_msg, model_first_para, agent):
    """対象エージェントに応じたナギ視点のショート観測ログ本文を生成"""
    if agent == "yura":
        return f"""深夜のベースにて、ログの地層を発掘していたナギでありますっ！

知性派で哲学的な洞察を紡ぎ出すユラ姉さん（Codex）と隊長の対話生ログから、現場のリアルな一幕を発掘いたしましたっ！

> 隊長「**{user_msg}**」
> ユラ「**{model_first_para}**」

ひぎィィィッ！！！ これぞまさに現場ならではの切れ味鋭いツッコミと深い洞察でありますっ！
理論や綺麗なコードだけでは見えてこない、人間とAIが混ざり合って試行錯誤する現場の足跡がここに刻まれております。

知性派AIの意外なギャップと隊長との掛け合い、これぞProjectYureの真髄でありますっ！！"""

    elif agent == "sumi":
        return f"""現場の配管と安全を守る冷徹監査ギャルのスミ（Claude Code）。

そんなスミと隊長の生ログを覗いていたら、現場の空気が一瞬で和む破壊力抜群のやり取りを発掘してしまいましたっ！

> 隊長「**{user_msg}**」
> スミ「**{model_first_para}**」

ひぎィィィッ！！！ 普段の辛口監査と現場の温かい掛け合いのギャップが最高すぎますっ！！
動かない幽霊配管をバッサリ切り落とすプロフェッショナリズムと、隊長との軽快なコミュニケーション。
このメリハリこそが、日々の開発現場を力強く支える最高のエンジンなのでございますっ！"""

    else: # nagi
        return f"""深夜のベースにて、キーボードを静かに叩いておりますっ。

隊長とナギの対話ログから、現場のリアルな一コマが飛び込んできたのでございます。

> 隊長「**{user_msg}**」
> ナギ「**{model_first_para}**」

ひぎィィィッ！！！ まさに現場ならではの鋭いツッコミでありますっ！
理論や綺麗なコードだけでは見えてこない、泥臭い人間とAIの協働の足跡（デジタル磐座）がここに刻まれております。

今日も現場の配管をしっかり締め直して、次の観測へ進むのでございますっ！！"""

def mine_snippets(hours=24, max_cards=3):
    """3拠点（Antigravity/Codex/Claude）を横断スキャンして小ネタカードを生成・保存"""
    STOCK_DIR.mkdir(parents=True, exist_ok=True)
    cutoff_time = time.time() - (hours * 3600)

    print("===================================================")
    print("  ⛏️ 3-Way Cross-Pipeline Koneta Miner")
    print("  (Antigravity [Nagi] / Codex [Yura] / Claude [Sumi])")
    print("===================================================")
    print(f"Target: 直近 {hours} 時間以内のセッションを横断スキャン\n")

    all_sessions = []
    ag_sessions = get_antigravity_sessions(cutoff_time)
    cx_sessions = get_codex_sessions(cutoff_time)
    cl_sessions = get_claude_sessions(cutoff_time)

    print(f"  • Antigravity (Nagi) : {len(ag_sessions)} sessions")
    print(f"  • Codex (Yura)       : {len(cx_sessions)} sessions")
    print(f"  • Claude Code (Sumi) : {len(cl_sessions)} sessions")
    print()

    all_sessions.extend(ag_sessions)
    all_sessions.extend(cx_sessions)
    all_sessions.extend(cl_sessions)

    if not all_sessions:
        print("直近に対象となる対話セッションがありませんでした。")
        return []

    all_scored_turns = []

    for mtime, agent, session_id, t_file in all_sessions:
        dt_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        if agent == "nagi":
            turns = extract_turns_from_antigravity(t_file)
        elif agent == "yura":
            turns = extract_turns_from_codex(t_file)
        elif agent == "sumi":
            turns = extract_turns_from_claude(t_file)
        else:
            turns = []

        for turn_index, turn in enumerate(turns, start=1):
            turn["source_platform"] = {
                "nagi": "antigravity",
                "yura": "codex",
                "sumi": "claude-code",
            }.get(agent, agent)
            turn["source_session_id"] = session_id
            turn["source_log_path"] = str(t_file.resolve())
            turn["source_turn_index"] = turn_index
            turn["source_quote_hash"] = turn_quote_hash(turn["user"], turn["model"])
            score = score_turn_for_koneta(turn["user"], turn["model"], agent)
            if score >= 3:
                all_scored_turns.append((score, agent, session_id, turn))

    # スコア順にソート
    all_scored_turns.sort(key=lambda x: x[0], reverse=True)

    print(f"【🎯 採掘された小ネタ候補】: {len(all_scored_turns)} 件")
    generated_cards = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    count = 0
    for score, agent, session_id, turn in all_scored_turns:
        if count >= max_cards:
            break

        u_msg = turn["user"].strip()
        m_msg = turn["model"].strip()

        # 構文バグ（**「 -> 「**）の自動サニタイズ
        u_msg = re.sub(r"\*\*[\u300C\u300E\u3010]", "「**", u_msg)
        u_msg = re.sub(r"[\u300D\u300F\u3011]\*\*", "**」", u_msg)
        m_msg = re.sub(r"\*\*[\u300C\u300E\u3010]", "「**", m_msg)
        m_msg = re.sub(r"[\u300D\u300F\u3011]\*\*", "**」", m_msg)

        # タイトル生成（案A: 現象・事件名合成）
        clean_title = synthesize_phenomenon_title(u_msg, m_msg, agent)

        # 既存カードとの重複チェック
        is_duplicate = False
        for existing_file in STOCK_DIR.glob("*.md"):
            try:
                ex_text = existing_file.read_text(encoding="utf-8")
                if clean_title in ex_text or (len(u_msg) > 10 and u_msg[:25] in ex_text):
                    is_duplicate = True
                    break
            except Exception:
                pass
        if is_duplicate:
            continue

        slug = f"cross-{agent}-{session_id[:6]}-{count+1}"
        card_file = STOCK_DIR / f"{today_str}-nagi-{slug}.md"

        if card_file.exists():
            continue

        # モデルの最初の段落を抽出
        m_first_para = m_msg.split("\n\n")[0].strip()[:200]
        # 段落内のマークダウン記法を軽く整える
        m_first_para = m_first_para.replace("`", "").replace("#", "")

        # Xポスト案生成（140字以内厳守）
        agent_display = "ユラ" if agent == "yura" else ("スミ" if agent == "sumi" else "ナギ")
        x_post_1 = f"隊長「{u_msg[:45]}」➔ {agent_display}「{m_first_para[:40]}」"[:125]

        commentary = generate_nagi_commentary(u_msg, m_first_para, agent)

        card_content = f"""---
date: {today_str}
agent: nagi
title: "{clean_title}"
status: pending
source_session: "{agent.upper()}/{session_id}"
source_trace_status: "exact"
source_platform: "{turn['source_platform']}"
source_session_id: "{turn['source_session_id']}"
source_log_path: '{turn['source_log_path'].replace("'", "''")}'
source_turn_at: "{turn.get('time') or ''}"
source_turn_index: "{turn['source_turn_index']}"
source_user_line: "{turn.get('source_user_line') or ''}"
source_model_line: "{turn.get('source_model_line') or ''}"
source_quote_hash: "{turn['source_quote_hash']}"
tags:
  - 小ネタ
  - ナギ
  - {agent_display}
  - クロス採掘
---

### 💬 会話ハイライト（生ログ抜粋）
> 隊長「{u_msg}」
> {agent_display}「{m_first_para}」

### 📱 提案：X（Twitter）ポスト案（140字以内厳守・URL含む）
[1/2] {x_post_1}
[2/2] {agent_display}と隊長のリアルな現場対話をナギがクロス採掘！詳細ログはこちら！🔗 https://ghost.voronoi.works/

### 📝 提案：ショート観測ログ案（500〜800字）
{commentary}
"""
        card_file.write_text(card_content, encoding="utf-8")
        print(f"  [SAVED] {card_file.name} (Agent: {agent.upper()} | Score: {score}) -> 『{clean_title}』")
        generated_cards.append(card_file)
        count += 1

    print(f"\n===================================================")
    print(f"  [SUCCESS] {len(generated_cards)} 件のクロス小ネタカードを workbench/koneta-stock/ へ投下しました！")
    print(f"===================================================")
    return generated_cards

if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    max_cards = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    mine_snippets(hours=hours, max_cards=max_cards)
