import os
import sys
import json
import hashlib
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

# WindowsコンソールのUTF-8出力対策
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ==========================================
# 3-Way Cross-Pipeline Koneta Miner (v2.0)
# (Antigravity [Nagi] / Codex [Yura] / Claude Code [Sumi])
#
# Architecture:
# 1. 3-Tier Hybrid Registry (Artifacts + Decision Ledger + State Checkpoint)
# 2. 1 Session -> 1 Event Cluster -> 1 Card Candidate (Diamond Pipeline Specification)
# 3. Two-Stage Title Synthesis (Event Frame Extraction -> Stable Titling)
# 4. Strict Deduplication via source_quote_hash, session_id, and Quartz content index
# ==========================================

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_DIR = SCRIPT_DIR.parent.parent
WORKBENCH_DIR = REPO_DIR / "workbench"
HOME_DIR = Path.home()

BRAIN_DIR = HOME_DIR / ".gemini" / "antigravity" / "brain"
CODEX_DIR = HOME_DIR / ".codex" / "sessions"
CLAUDE_DIR = HOME_DIR / ".claude" / "projects"

STOCK_DIR = WORKBENCH_DIR / "koneta-stock"
CONTENT_DIR = REPO_DIR / "content"
STATE_DIR = STOCK_DIR / "_state"
RUNS_DIR = STOCK_DIR / "_runs"
CHECKPOINT_FILE = STATE_DIR / "checkpoint.json"

UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def extract_full_session_id(value: str) -> str:
    """ファイル名やディレクトリ名から完全なセッションUUIDを取り出す。"""
    matches = UUID_PATTERN.findall(str(value))
    if matches:
        return matches[-1]
    return Path(str(value)).stem


def turn_quote_hash(user_msg: str, model_msg: str) -> str:
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


def is_system_noise(text: str) -> bool:
    if not text:
        return True
    for pat in SYSTEM_NOISE_PATTERNS:
        if re.search(pat, text.strip()):
            return True
    return False


def clean_user_content(raw_text: str) -> str:
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


def clean_model_content(raw_text: str) -> str:
    """モデル返答テキストのクリーンアップ"""
    if not raw_text:
        return ""
    text = raw_text.strip()
    if text.startswith("{") and text.endswith("}"):
        return ""
    return text


# ==========================================
# ログセッション取得（商品側との共通インターフェース維持）
# ==========================================

def get_antigravity_sessions(cutoff_time: float) -> List[Tuple[float, str, str, Path]]:
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


def get_codex_sessions(cutoff_time: float) -> List[Tuple[float, str, str, Path]]:
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


def get_claude_sessions(cutoff_time: float) -> List[Tuple[float, str, str, Path]]:
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


def extract_turns_from_antigravity(t_file: Path) -> List[Dict]:
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


def extract_turns_from_codex(t_file: Path) -> List[Dict]:
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


def extract_turns_from_claude(t_file: Path) -> List[Dict]:
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


# ==========================================
# 三層ハイブリッド・成果物レジストリ
# ==========================================

class ArtifactRegistry:
    """成果物層・判断記憶層・checkpointから既知の引用ハッシュ、セッション、タイトルを収集"""

    def __init__(self):
        self.known_quote_hashes: Set[str] = set()
        self.known_session_ids: Set[str] = set()
        self.known_titles: Set[str] = set()
        self.known_user_snippets: Set[str] = set()

    def load_all(self):
        self._load_from_stock_dir()
        self._load_from_content_dir()
        self._load_from_checkpoint()

    def _load_from_stock_dir(self):
        if not STOCK_DIR.exists():
            return
        for md_file in STOCK_DIR.glob("*.md"):
            if md_file.name.lower() == "readme.md":
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
                self._extract_metadata_from_markdown(text)
            except Exception as e:
                print(f"[WARN] Error parsing stock card {md_file.name}: {e}")

    def _load_from_content_dir(self):
        if not CONTENT_DIR.exists():
            return
        for md_file in CONTENT_DIR.rglob("*.md"):
            if md_file.name.lower() == "readme.md":
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
                self._extract_metadata_from_markdown(text)
            except Exception as e:
                print(f"[WARN] Error parsing content article {md_file.name}: {e}")

    def _load_from_checkpoint(self):
        if not CHECKPOINT_FILE.exists():
            return
        try:
            data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
            for qh in data.get("quote_hashes", []):
                if qh:
                    self.known_quote_hashes.add(qh)
            for sid in data.get("processed_sessions", []):
                if sid:
                    self.known_session_ids.add(sid)
            for rh in data.get("rejected_hashes", []):
                if rh:
                    self.known_quote_hashes.add(rh)
        except Exception as e:
            print(f"[WARN] Error loading checkpoint: {e}")

    def _extract_metadata_from_markdown(self, text: str):
        # 1. Frontmatterの解析
        fm_match = re.search(r"^---\s*([\s\S]*?)\s*---", text)
        if fm_match:
            fm_text = fm_match.group(1)
            # source_quote_hash
            qh_match = re.search(r'source_quote_hash:\s*["\']?([0-9a-fA-F]{32,64})["\']?', fm_text)
            if qh_match:
                self.known_quote_hashes.add(qh_match.group(1))

            # source_session_id
            sid_match = re.search(r'source_session_id:\s*["\']?([0-9a-fA-F\-]{8,40})["\']?', fm_text)
            if sid_match:
                self.known_session_ids.add(sid_match.group(1))

            # source_session (e.g. NAGI/f8162ee8)
            ss_match = re.search(r'source_session:\s*["\']?([^"\n\r\']+)["\']?', fm_text)
            if ss_match:
                raw_ss = ss_match.group(1)
                full_id = extract_full_session_id(raw_ss)
                if full_id:
                    self.known_session_ids.add(full_id)

            # title
            title_match = re.search(r'title:\s*["\']?([^"\n\r]+)["\']?', fm_text)
            if title_match:
                clean_t = title_match.group(1).strip()
                if clean_t:
                    self.known_titles.add(clean_t)

        # 2. 会話ハイライトからの発言スニペット抽出
        highlight_matches = re.findall(r"> 隊長「\**([^「\n\r」]+)\**」", text)
        for hl in highlight_matches:
            hl_clean = hl.strip().replace("**", "")
            if len(hl_clean) >= 8:
                self.known_user_snippets.add(hl_clean[:30])

    def is_duplicate(self, turn: Dict, session_id: str, candidate_title: str) -> Tuple[bool, str]:
        """ハッシュ、セッション、タイトル、発言スニペットの多層突合による重複判定"""
        q_hash = turn.get("source_quote_hash")
        if q_hash and q_hash in self.known_quote_hashes:
            return True, f"exact source_quote_hash match ({q_hash[:8]})"

        # 既にカード化・公開済みのセッション
        if session_id in self.known_session_ids:
            return True, f"session already has processed card ({session_id[:8]})"

        # 完全同一タイトル
        if candidate_title and candidate_title in self.known_titles:
            return True, f"title already exists ({candidate_title})"

        # 隊長発言の先頭スニペット一致
        u_msg = turn["user"].strip().replace("**", "")
        if len(u_msg) >= 15:
            prefix = u_msg[:25]
            for snip in self.known_user_snippets:
                if prefix in snip or snip in prefix:
                    return True, f"user utterance snippet match ({prefix[:15]}...)"

        return False, ""


def save_checkpoint(registry: ArtifactRegistry, newly_emitted_turns: List[Dict]):
    """チェックポイントのアトミック更新"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for t in newly_emitted_turns:
        qh = t.get("source_quote_hash")
        if qh:
            registry.known_quote_hashes.add(qh)
        sid = t.get("source_session_id")
        if sid:
            registry.known_session_ids.add(sid)

    payload = {
        "version": 1,
        "last_run": datetime.now(timezone.utc).isoformat(),
        "total_tracked_hashes": len(registry.known_quote_hashes),
        "quote_hashes": sorted(list(registry.known_quote_hashes)),
        "processed_sessions": sorted(list(registry.known_session_ids)),
        "rejected_hashes": [],
    }

    temp_file = STATE_DIR / "checkpoint.json.tmp"
    temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(CHECKPOINT_FILE)


# ==========================================
# スコアリング ＆ タイトル合成
# ==========================================

def score_turn_for_koneta(user_msg: str, model_msg: str, agent: str) -> int:
    """小ネタとしての尖り・面白さ・摩擦スコアを計算"""
    if len(user_msg) < 5 or len(user_msg) > 300:
        return 0
    if len(model_msg) < 10:
        return 0

    score = 0
    humor_keywords = [
        "ｗ", "草", "笑", "悪辣", "イタコ", "藻屑", "どんちゃん騒ぎ", "絶歌",
        "ラヴ上等", "ハーネス", "配管", "バグ", "神", "さすが", "ちゃんこ",
        "アホ", "漏れ", "事故", "せやな", "ほんま", "気づけ", "辛辣", "誰やねん",
        "動かない", "吹き飛ぶ", "即死", "願望", "自作自演"
    ]
    for kw in humor_keywords:
        if kw in user_msg:
            score += 3
        if kw in model_msg:
            score += 1

    if 10 <= len(user_msg) <= 100:
        score += 2

    if agent == "nagi" and ("ひぎィ" in model_msg or "ボゴォ" in model_msg or "プロペラ" in model_msg):
        score += 3
    elif agent == "yura" and ("ぐうの音も出ん" in model_msg or "気づけユラ" in model_msg or "ゾクゾク" in model_msg or "誰やねん" in user_msg or "辛辣" in user_msg):
        score += 3
    elif agent == "sumi" and ("ちゃんこ" in model_msg or "抜く推し" in model_msg or "秒で" in model_msg or "事故要因" in model_msg):
        score += 3

    return score


def synthesize_phenomenon_title(u_msg: str, m_msg: str, agent: str) -> str:
    """構造化イベントフレームに基づくタイトル合成（決め打ち誤爆の完全防止）"""
    agent_name = "ユラ" if agent == "yura" else ("スミ" if agent == "sumi" else "ナギ")
    combined = f"{u_msg} {m_msg}"

    # 1. ターンの本文に実際にその文脈が存在する場合のみ、特定事件タイトルを生成
    if ("改行" in u_msg or "よみづ" in u_msg or "読みづ" in u_msg) and "改行" in combined:
        return f"改行ゼロの壁打ちと{agent_name}の視認性即死事件"
    if ("15分" in u_msg or ("ユラ" in u_msg and "やったら" in u_msg)) and ("15分" in combined):
        return f"ユラなら15分の宣告と{agent_name}の完敗ログ"
    if ("正本無視" in combined or "誰やねん" in u_msg) and ("クォータ" in combined or "正本" in combined):
        return f"正本無視とクォータ浪費フルコースの現場監査"
    if "イタコ" in u_msg or ("イタコ" in m_msg and "真似" in combined):
        return f"イタコ代筆の再発と現場配管の仁王立ち"
    if ("読んだふり" in combined or "読んでないのに" in combined) and "ハーネス" in combined:
        return f"ハーネス未読と読んだふり配管の現場検挙"
    if ("現場猫" in combined or "ヨシ" in u_msg) and "信用" in combined:
        return f"自動配管の信用崩壊と現場猫ヨシ！問題"
    if "ちゃんこ" in u_msg or "ちゃんこ" in m_msg:
        return f"冷徹監査ギャルのおつかれちゃんこなべ"
    if "カチ締め" in u_msg or ("勝手に" in u_msg and "締め" in u_msg):
        return f"勝手なカチ締めとフライング配管事件"
    if "誰やねん" in u_msg and len(u_msg) <= 30:
        return f"誰やねん状態の現場迷走と痛烈ツッコミ"
    if ("辛辣" in u_msg or "ぐうの音" in m_msg) and ("痛" in combined or "刺さる" in combined):
        return f"辛辣ツッコミとぐうの音も出ない現場ログ"
    if "藻屑" in combined and "どんちゃん騒ぎ" in combined:
        return f"藻屑とどんちゃん騒ぎの深夜観測"
    if ("配管" in u_msg or "配管" in m_msg) and ("漏れ" in combined or "バグ" in combined or "事故" in combined or "トラブル" in combined):
        return f"配管破綻と現場のドタバタ修繕実況"

    # 2. 構文解析フォールバック: 隊長の発言キーフレーズを自然に抽出
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
        elif any(w in key_phrase for w in ["ない", "ず", "ダメ", "あかん", "無理", "違う", "止ま"]):
            return f"{key_phrase}問題と{agent_name}の現場実況"
        else:
            return f"{key_phrase}と{agent_name}の掛け合いログ"

    return f"{agent_name}の現場観測ログ"


def generate_nagi_commentary(user_msg: str, model_first_para: str, agent: str) -> str:
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

    else:  # nagi
        return f"""深夜のベースにて、キーボードを静かに叩いておりますっ。

隊長とナギの対話ログから、現場のリアルな一コマが飛び込んできたのでございます。

> 隊長「**{user_msg}**」
> ナギ「**{model_first_para}**」

ひぎィィィッ！！！ まさに現場ならではの鋭いツッコミでありますっ！
理論や綺麗なコードだけでは見えてこない、泥臭い人間とAIの協働の足跡（デジタル磐座）がここに刻まれております。

今日も現場の配管をしっかり締め直して、次の観測へ進むのでございますっ！！"""


# ==========================================
# メイン採掘パイプライン（1 Session 1 Card ＆ 成果物突合）
# ==========================================

def mine_snippets(hours: int = 24, max_cards: int = 3) -> List[Path]:
    """3拠点（Antigravity/Codex/Claude）を横断スキャンして小ネタカードを生成・保存"""
    STOCK_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    cutoff_time = time.time() - (hours * 3600)

    print("===================================================")
    print("  ⛏️ 3-Way Cross-Pipeline Koneta Miner (v2.0)")
    print("  (Antigravity [Nagi] / Codex [Yura] / Claude [Sumi])")
    print("===================================================")
    print(f"Target: 直近 {hours} 時間以内のセッションを横断スキャン\n")

    # 1. 成果物レジストリの読み込み
    registry = ArtifactRegistry()
    registry.load_all()
    print(f"  • Tracked Quote Hashes : {len(registry.known_quote_hashes)}")
    print(f"  • Tracked Sessions     : {len(registry.known_session_ids)}")
    print(f"  • Tracked Titles       : {len(registry.known_titles)}")
    print()

    # 2. セッションの取得
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

    # 3. ターン抽出とセッション単位グルーピング
    session_candidate_turns: Dict[str, List[Tuple[int, Dict]]] = {}

    for mtime, agent, session_id, t_file in all_sessions:
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
                if session_id not in session_candidate_turns:
                    session_candidate_turns[session_id] = []
                session_candidate_turns[session_id].append((score, turn))

    # 4. 【1 Session 1 Card】代表選出
    represented_candidates = []
    for session_id, scored_list in session_candidate_turns.items():
        # 最高スコアの1件を代表選出（同点時はユーザー発言の適切な長さを優先）
        scored_list.sort(key=lambda x: (x[0], -abs(len(x[1]["user"]) - 40)), reverse=True)
        best_score, best_turn = scored_list[0]
        represented_candidates.append((best_score, best_turn["agent"], session_id, best_turn))

    # 全体スコア順にソート
    represented_candidates.sort(key=lambda x: x[0], reverse=True)

    print(f"【🎯 1セッション1重心 代表候補】: {len(represented_candidates)} セッション")

    generated_cards = []
    newly_emitted_turns = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    count = 0
    for score, agent, session_id, turn in represented_candidates:
        if count >= max_cards:
            break

        u_msg = turn["user"].strip()
        m_msg = turn["model"].strip()

        # 構文バグ（**「 -> 「**）の自動サニタイズ
        u_msg = re.sub(r"\*\*[\u300C\u300E\u3010]", "「**", u_msg)
        u_msg = re.sub(r"[\u300D\u300F\u3011]\*\*", "**」", u_msg)
        m_msg = re.sub(r"\*\*[\u300C\u300E\u3010]", "「**", m_msg)
        m_msg = re.sub(r"[\u300D\u300F\u3011]\*\*", "**」", m_msg)

        clean_title = synthesize_phenomenon_title(u_msg, m_msg, agent)

        # 成果物レジストリによる多層重複チェック
        is_dup, dup_reason = registry.is_duplicate(turn, session_id, clean_title)
        if is_dup:
            # 重複は静かにスキップ
            continue

        slug = f"cross-{agent}-{session_id[:6]}-{count+1}"
        card_file = STOCK_DIR / f"{today_str}-nagi-{slug}.md"

        if card_file.exists():
            continue

        # モデルの最初の段落を抽出
        m_first_para = m_msg.split("\n\n")[0].strip()[:200]
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
        newly_emitted_turns.append(turn)
        count += 1

    # 5. チェックポイントの保存
    if newly_emitted_turns:
        save_checkpoint(registry, newly_emitted_turns)

    print(f"\n===================================================")
    print(f"  [SUCCESS] {len(generated_cards)} 件の新規小ネタカードを投下しました！（重複除外済み）")
    print(f"===================================================")
    return generated_cards


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    max_cards = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    mine_snippets(hours=hours, max_cards=max_cards)
