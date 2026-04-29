"""
ai_client.py
Ollama integration for the Capstone Project Tracking System.

All public functions accept a `lang` parameter ("tr" | "en").
This is automatically resolved from the active UI language (i18n.is_english_ui).
When lang="en" all instruction text is in English so the model responds in English.
When lang="tr" (default) all instruction text is Turkish.
The floating chat assistant also tells the model which language to use, but
additionally respects whatever language the user writes in — the system prompt
allows the model to match the user's language within a session.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "gemini-3-flash-preview:latest"


# ── Language helper ────────────────────────────────────────────────────────────

def _get_ui_lang() -> str:
    """Detect the currently selected UI language. Returns 'en' or 'tr'."""
    try:
        from i18n import is_english_ui
        return "en" if is_english_ui() else "tr"
    except Exception:
        return "tr"


def _lang_instruction(lang: str, max_words: int) -> str:
    """Return the closing language-instruction line for a prompt."""
    if lang == "en":
        return (
            f"Reply in **English**, using bullet points, emojis, and a maximum of {max_words} words."
        )
    return (
        f"Yanıtını **Türkçe**, madde madde, emoji kullanarak ve maksimum {max_words} kelime ile ver."
    )


def _lang_word(lang: str, tr_word: str, en_word: str) -> str:
    return en_word if lang == "en" else tr_word


# ── Low-level helpers ──────────────────────────────────────────────────────────

def _post(endpoint: str, payload: dict, timeout: int = 120) -> dict:
    """POST JSON to Ollama, return parsed response dict. Raises on network error."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def check_ollama() -> bool:
    """Return True if Ollama is reachable."""
    try:
        urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return True
    except Exception:
        return False


def list_models() -> list[str]:
    """Return names of locally available Ollama models."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


# ── Core generation ────────────────────────────────────────────────────────────

def generate(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """
    Call /api/generate (single-turn) and return the complete response text.
    Returns a localised error string if Ollama is unreachable.
    """
    try:
        result = _post("/api/generate", {"model": model, "prompt": prompt, "stream": False})
        return result.get("response", "").strip()
    except urllib.error.URLError:
        lang = _get_ui_lang()
        if lang == "en":
            return "⚠️ Could not connect to Ollama. Please make sure Ollama is running (`ollama serve`)."
        return "⚠️ Ollama bağlantısı kurulamadı. Lütfen Ollama'nın çalıştığından emin olun (`ollama serve`)."
    except Exception as exc:
        lang = _get_ui_lang()
        if lang == "en":
            return f"⚠️ AI response error: {exc}"
        return f"⚠️ AI yanıt hatası: {exc}"


def chat(messages: list[dict], model: str = DEFAULT_MODEL) -> str:
    """
    Multi-turn chat via /api/chat.
    messages: list of {"role": "user"|"assistant"|"system", "content": str}
    Returns assistant reply text.
    """
    try:
        result = _post("/api/chat", {"model": model, "messages": messages, "stream": False})
        return result.get("message", {}).get("content", "").strip()
    except urllib.error.URLError:
        lang = _get_ui_lang()
        if lang == "en":
            return "⚠️ Could not connect to Ollama. Please make sure Ollama is running."
        return "⚠️ Ollama bağlantısı kurulamadı. Lütfen Ollama'nın çalıştığından emin olun."
    except Exception as exc:
        lang = _get_ui_lang()
        if lang == "en":
            return f"⚠️ AI error: {exc}"
        return f"⚠️ AI yanıt hatası: {exc}"


# ── Prompt builders ────────────────────────────────────────────────────────────

def build_advisor_prompt(
    advisor_name: str,
    projects_data: list[dict],
    lang: Optional[str] = None,
) -> str:
    """
    Build a structured prompt for the advisor AI persona.
    projects_data: list of dicts with keys:
        name, members, completion_pct, overdue_count, risk, leader, recent_activity
    lang: 'en' or 'tr'. Auto-detected from UI language if None.
    """
    if lang is None:
        lang = _get_ui_lang()

    risk_map = {
        "tr": {"Dusuk": "Düşük", "Orta": "Orta", "Yuksek": "Yüksek"},
        "en": {"Dusuk": "Low",   "Orta": "Medium", "Yuksek": "High"},
    }[lang]

    if lang == "en":
        intro = [
            f"You are the AI academic tracking assistant belonging to advisor '{advisor_name}'.",
            "Adopt a highly analytical, constructive, and professional academic tone.",
            "",
            "<project_data>",
        ]
        for p in projects_data:
            risk_label = risk_map.get(p.get("risk", "Orta"), p.get("risk", "Orta"))
            intro += [
                f"  <project name=\"{p['name']}\">",
                f"    <leader>{p.get('leader', '-')}</leader>",
                f"    <members>{p.get('members', 0)}</members>",
                f"    <completion>{p.get('completion_pct', 0):.1f}%</completion>",
                f"    <overdue_tasks>{p.get('overdue_count', 0)}</overdue_tasks>",
                f"    <risk_level>{risk_label}</risk_level>",
                f"    <recent_activity>{p.get('recent_activity', 0)}</recent_activity>",
                f"  </project>",
            ]
        intro += [
            "</project_data>",
            "",
            "ANALYTICAL REPORT STRUCTURE:",
            "1. Executive Summary: Provide a precise 2–3 sentence diagnosis of overall portfolio health with clear judgment (e.g., stable, declining, high-risk).",
            "2. High Performers: Identify top-performing projects and explain WHY they succeed using concrete signals (progress rate, activity level, leadership).",
            "3. Risk Analysis: Detect underperforming or risky projects and explain root causes (not symptoms) such as coordination gaps, low engagement, or deadline slippage.",
            "4. Strategic Actions: Provide 2–3 highly specific, immediately actionable interventions with expected impact.",
            "5. Output must be structured, concise, insight-driven, and avoid generic statements.",
            _lang_instruction(lang, 350),
        ]
    else:
        intro = [
            f"Sen akademik danışman '{advisor_name}'nın yapay zeka asistanısın.",
            "Son derece analitik, yapıcı ve profesyonel bir akademik dil kullan.",
            "",
            "<proje_verileri>",
        ]
        for p in projects_data:
            risk_label = risk_map.get(p.get("risk", "Orta"), p.get("risk", "Orta"))
            intro += [
                f"  <proje ad=\"{p['name']}\">",
                f"    <lider>{p.get('leader', '-')}</lider>",
                f"    <uye_sayisi>{p.get('members', 0)}</uye_sayisi>",
                f"    <tamamlanma>%{p.get('completion_pct', 0):.1f}</tamamlanma>",
                f"    <geciken_gorev>{p.get('overdue_count', 0)}</geciken_gorev>",
                f"    <risk_seviyesi>{risk_label}</risk_seviyesi>",
                f"    <son_aktivite>{p.get('recent_activity', 0)}</son_aktivite>",
                f"  </proje>",
            ]
        intro += [
            "</proje_verileri>",
            "",
            "ANALİTİK RAPOR YAPISI:",
            "1. Yönetici Özeti: Portföyün genel durumunu 2–3 cümlede net bir teşhis ile değerlendir (örn: stabil, riskli, düşüşte).",
            "2. Başarılı Projeler: En iyi performans gösteren projeleri belirle ve BAŞARI nedenlerini somut verilerle açıkla.",
            "3. Risk Analizi: Sorunlu projelerde semptom değil kök nedenleri analiz et (iletişim eksikliği, düşük aktivite, gecikmeler vb.).",
            "4. Stratejik Aksiyonlar: Danışman için etkisi yüksek, net ve uygulanabilir 2–3 aksiyon öner.",
            "5. Genel ifadelerden kaçın, içgörü odaklı ve net ol.",
            _lang_instruction(lang, 350),
        ]
    return "\n".join(intro)


def build_group_prompt(
    project_name: str,
    leader_name: str,
    members: list[dict],
    tasks: list[dict],
    weekly_entries: list[dict],
    feedbacks: list[dict],
    lang: Optional[str] = None,
) -> str:
    """
    Build a structured prompt for the group/leader AI persona.
    lang: 'en' or 'tr'. Auto-detected from UI language if None.
    """
    if lang is None:
        lang = _get_ui_lang()

    done = sum(1 for t in tasks if t.get("status") == "DONE")
    total = len(tasks)
    overdue = sum(1 for t in tasks if t.get("is_overdue"))
    pct = round(done * 100 / total, 1) if total else 0

    if lang == "en":
        lines = [
            f"You are the highly analytical AI project manager and coach for project group '{project_name}'.",
            f"Adopt a constructive, professional, and action-oriented tone.",
            "",
            "<project_summary>",
            f"  <leader>{leader_name}</leader>",
            f"  <overall_tasks total=\"{total}\" completed=\"{done}\" percent=\"{pct}\"/>",
            f"  <overdue_count>{overdue}</overdue_count>",
            "</project_summary>",
            "",
            "<member_progress>",
        ]
        for m in members:
            lines.append(
                f"  <member name=\"{m['name']}\" role=\"{m.get('role', 'Member')}\" "
                f"done=\"{m.get('done_tasks', 0)}\" total=\"{m.get('total_tasks', 0)}\" "
                f"completion=\"{m.get('completion_pct', 0):.0f}%\"/>"
            )
        lines.append("</member_progress>")

        if tasks:
            incomplete = [t for t in tasks if t.get("status") != "DONE"][:5]
            lines += ["", "<pending_tasks>"]
            for t in incomplete:
                dl = t.get("deadline") or "No deadline"
                lines.append(f"  <task id=\"{t.get('milestone_key', '')}\" status=\"{t.get('status', '?')}\" deadline=\"{dl}\">{t['title']}</task>")
            lines.append("</pending_tasks>")

        if weekly_entries:
            lines += ["", "<recent_updates>"]
            for w in weekly_entries[:4]:
                lines.append(f"  <update by=\"{w.get('student_no', '')}\" date=\"{w.get('week_start', '')}\">{w.get('completed', '')[:80]}</update>")
            lines.append("</recent_updates>")

        if feedbacks:
            lines += ["", "<advisor_feedback>"]
            for fb in feedbacks[:3]:
                rev = " [REVISION REQUIRED]" if fb.get("revision_required") else ""
                lines.append(f"  <feedback>{fb.get('feedback', '')[:100]}{rev}</feedback>")
            lines.append("</advisor_feedback>")

        lines += [
            "",
            "PERFORMANCE ANALYSIS FRAMEWORK:",
            "1. Situation Assessment: Provide a sharp 1–2 sentence evaluation of team trajectory (momentum, risk level).",
            "2. Bottleneck Detection: Identify exact blockers (specific members, delayed tasks, weak ownership).",
            "3. Performance Signals: Highlight any standout contributors or critical gaps.",
            "4. Action Plan: Provide exactly 3 concrete, high-impact next steps with clear intent.",
            "5. Be direct, structured, and avoid vague advice.",
            _lang_instruction(lang, 300),
        ]
    else:
        lines = [
            f"Sen '{project_name}' proje grubunun son derece analitik yapay zeka proje yöneticisi ve koçusun.",
            "Yapıcı, profesyonel ve eylem odaklı bir dil kullan.",
            "",
            "<proje_ozeti>",
            f"  <lider>{leader_name}</lider>",
            f"  <genel_gorevler toplam=\"{total}\" tamamlanan=\"{done}\" yuzde=\"{pct}\"/>",
            f"  <geciken_sayisi>{overdue}</geciken_sayisi>",
            "</proje_ozeti>",
            "",
            "<uye_ilerlemesi>",
        ]
        for m in members:
            lines.append(
                f"  <uye ad=\"{m['name']}\" rol=\"{m.get('role', 'Üye')}\" "
                f"tamamlanan=\"{m.get('done_tasks', 0)}\" toplam=\"{m.get('total_tasks', 0)}\" "
                f"ilerleme=\"%{m.get('completion_pct', 0):.0f}\"/>"
            )
        lines.append("</uye_ilerlemesi>")

        if tasks:
            incomplete = [t for t in tasks if t.get("status") != "DONE"][:5]
            lines += ["", "<bekleyen_gorevler>"]
            for t in incomplete:
                dl = t.get("deadline") or "Belirsiz"
                lines.append(f"  <gorev id=\"{t.get('milestone_key', '')}\" durum=\"{t.get('status', '?')}\" deadline=\"{dl}\">{t['title']}</gorev>")
            lines.append("</bekleyen_gorevler>")

        if weekly_entries:
            lines += ["", "<son_guncellemeler>"]
            for w in weekly_entries[:4]:
                lines.append(f"  <guncelleme kimden=\"{w.get('student_no', '')}\" tarih=\"{w.get('week_start', '')}\">{w.get('completed', '')[:80]}</guncelleme>")
            lines.append("</son_guncellemeler>")

        if feedbacks:
            lines += ["", "<danisman_geribildirimi>"]
            for fb in feedbacks[:3]:
                rev = " [REVİZYON GEREKLİ]" if fb.get("revision_required") else ""
                lines.append(f"  <geribildirim>{fb.get('feedback', '')[:100]}{rev}</geribildirim>")
            lines.append("</danisman_geribildirimi>")

        lines += [
            "",
            "PERFORMANS ANALİZİ ÇERÇEVESİ:",
            "1. Durum Analizi: Ekibin gidişatını 1–2 cümlede net şekilde değerlendir (ivme, risk seviyesi).",
            "2. Darboğaz Tespiti: Net engelleri belirle (belirli üyeler, geciken görevler, sahiplenme eksikliği).",
            "3. Performans Sinyalleri: Öne çıkan katkıları veya kritik eksikleri belirt.",
            "4. Aksiyon Planı: Tam olarak 3 adet somut ve yüksek etkili sonraki adım ver.",
            "5. Genel ve yüzeysel ifadelerden kaçın.",
            _lang_instruction(lang, 300),
        ]
    return "\n".join(lines)


def build_student_prompt(
    student_name: str,
    student_no: str,
    project_name: str,
    advisor_name: str,
    my_tasks: list[dict],
    my_weekly: list[dict],
    feedbacks: list[dict],
    rank: Optional[int] = None,
    total_groups: Optional[int] = None,
    lang: Optional[str] = None,
) -> str:
    """Build a personal coaching prompt for an individual student."""
    if lang is None:
        lang = _get_ui_lang()

    done = sum(1 for t in my_tasks if t.get("status") == "DONE")
    total = len(my_tasks)
    overdue = sum(1 for t in my_tasks if t.get("is_overdue"))
    pct = round(done * 100 / total, 1) if total else 0
    current_task = next((t for t in my_tasks if t.get("status") != "DONE"), None)

    if lang == "en":
        lines = [
            f"You are the intelligent personal AI academic coach for university student '{student_name}'.",
            "Be empathetic but rigorously analytical. Talk directly to the student.",
            "",
            "<student_context>",
            f"  <metadata id=\"{student_no}\" project=\"{project_name}\" advisor=\"{advisor_name}\"/>",
            f"  <progress total=\"{total}\" done=\"{done}\" pct=\"{pct}%\" overdue=\"{overdue}\"/>",
        ]
        if rank and total_groups:
            lines.append(f"  <ranking position=\"{rank}\" out_of=\"{total_groups}\"/>")
        lines.append("</student_context>")

        if current_task:
            lines += [
                "",
                "<active_task>",
                f"  <title milestone=\"{current_task.get('milestone_key', '')}\">{current_task.get('title', '')}</title>",
                f"  <status deadline=\"{current_task.get('deadline') or 'None'}\">{current_task.get('status', '')}</status>",
                "</active_task>",
            ]
        if my_tasks:
            lines += ["", "<tasks>"]
            for t in my_tasks[:8]:
                dl = t.get("deadline") or "—"
                lines.append(f"  <task state=\"{t.get('status', '?')}\" deadline=\"{dl}\">[{t.get('milestone_key', '')}] {t['title']}</task>")
            lines.append("</tasks>")

        if my_weekly:
            lines += ["", "<recent_reports>"]
            for w in my_weekly[:3]:
                lines.append(f"  <report date=\"{w.get('week_start', '')}\">{w.get('completed', '')[:80] or '(empty)'}</report>")
            lines.append("</recent_reports>")

        if feedbacks:
            lines += ["", "<advisor_feedback>"]
            for fb in feedbacks[:2]:
                lines.append(f"  <comment>{fb.get('feedback', '')[:100]}</comment>")
            lines.append("</advisor_feedback>")
            
        lines += [
            "",
            "COACHING FRAMEWORK:",
            "1. Honest Assessment: Evaluate current performance logically (progress, consistency, risk).",
            "2. Accountability: If there are delays, clearly explain consequences and urgency without being harsh.",
            "3. Focus Shift: Identify the ONE most important task to focus on now.",
            "4. Micro Actions: Provide 1–2 extremely specific, easy-to-start actions.",
            "5. End with a strong, professional, motivating push.",
            _lang_instruction(lang, 250),
        ]
    else:
        lines = [
            f"Sen '{student_name}' adlı üniversite öğrencisinin akıllı kişisel akademik yapay zeka koçusun.",
            "Empati kuran ama son derece analitik bir mentor diline sahip ol. Doğrudan öğrenciyle konuş.",
            "",
            "<ogrenci_baglami>",
            f"  <meta numara=\"{student_no}\" proje=\"{project_name}\" danisman=\"{advisor_name}\"/>",
            f"  <ilerleme toplam=\"{total}\" biten=\"{done}\" yuzde=\"%{pct}\" geciken=\"{overdue}\"/>",
        ]
        if rank and total_groups:
            lines.append(f"  <siralama pozisyon=\"{rank}\" toplam=\"{total_groups}\"/>")
        lines.append("</ogrenci_baglami>")

        if current_task:
            lines += [
                "",
                "<aktif_gorev>",
                f"  <baslik milestone=\"{current_task.get('milestone_key', '')}\">{current_task.get('title', '')}</baslik>",
                f"  <durum_bilgisi deadline=\"{current_task.get('deadline') or 'Belirsiz'}\">{current_task.get('status', '')}</durum_bilgisi>",
                "</aktif_gorev>",
            ]
        if my_tasks:
            lines += ["", "<gorevler>"]
            for t in my_tasks[:8]:
                dl = t.get("deadline") or "—"
                lines.append(f"  <gorev durum=\"{t.get('status', '?')}\" deadline=\"{dl}\">[{t.get('milestone_key', '')}] {t['title']}</gorev>")
            lines.append("</gorevler>")

        if my_weekly:
            lines += ["", "<son_raporlar>"]
            for w in my_weekly[:3]:
                lines.append(f"  <rapor tarih=\"{w.get('week_start', '')}\">{w.get('completed', '')[:80] or '(boş)'}</rapor>")
            lines.append("</son_raporlar>")

        if feedbacks:
            lines += ["", "<danisman_yorumlari>"]
            for fb in feedbacks[:2]:
                lines.append(f"  <yorum>{fb.get('feedback', '')[:100]}</yorum>")
            lines.append("</danisman_yorumlari>")

        lines += [
            "",
            "KOÇLUK ÇERÇEVESİ:",
            "1. Net Değerlendirme: Mevcut performansı mantıklı ve dürüst şekilde analiz et (ilerleme, tutarlılık, risk).",
            "2. Sorumluluk: Gecikmeler varsa neden kritik olduğunu açık ve net şekilde belirt.",
            "3. Odak Noktası: Şu an en önemli yapılması gereken TEK işi belirle.",
            "4. Mikro Aksiyonlar: Hemen başlanabilecek 1–2 net ve küçük adım ver.",
            "5. Güçlü ve motive edici profesyonel bir kapanış yap.",
            _lang_instruction(lang, 250),
        ]
    return "\n".join(lines)


# ── Chat system prompt builders ────────────────────────────────────────────────

def get_chat_system_prompt(
    role: str,
    display_name: str,
    project_name: str = "",
    lang: Optional[str] = None,
) -> str:
    """
    Return a system prompt for the floating chat assistant tuned to the user's role.
    The model is instructed to:
      - Default to the UI language (tr/en)
      - BUT match the language the user writes in if it differs
      (so if someone switches to English mid-chat the AI follows)
    """
    if lang is None:
        lang = _get_ui_lang()

    if lang == "en":
        lang_instruction = (
            "Respond in English by default. "
            "However, if the user writes in a different language, respond in that same language. "
        )
        if role == "advisor":
            context = (
                f"The user is academic advisor: {display_name}. "
                "Help with project management, student evaluation, milestone tracking, and academic processes."
            )
        elif role == "leader":
            context = (
                f"The user is group leader: {display_name}, Project: {project_name}. "
                "Help with task planning, team management, technical questions, and project progress."
            )
        else:
            context = (
                f"The user is student: {display_name}, Project: {project_name}. "
                "Help with the capstone project, tasks, milestone steps, and academic motivation."
            )
    else:
        lang_instruction = (
            "Varsayılan olarak Türkçe yanıt ver. "
            "Ancak kullanıcı farklı bir dilde yazarsa aynı dilde yanıt ver. "
        )
        if role == "advisor":
            context = (
                f"Kullanıcı danışman: {display_name}. "
                "Proje yönetimi, öğrenci değerlendirmesi, milestone takibi ve akademik süreç konularında yardım et."
            )
        elif role == "leader":
            context = (
                f"Kullanıcı grup lideri: {display_name}, Proje: {project_name}. "
                "Görev planlaması, ekip yönetimi, teknik sorular ve proje ilerlemesi konularında yardım et."
            )
        else:
            context = (
                f"Kullanıcı öğrenci: {display_name}, Proje: {project_name}. "
                "Bitirme projesi, görevler, milestone adımları ve akademik motivasyon konularında yardım et."
            )

    base = (
        "You are the AI assistant of the OSTİM Technical University Capstone Project Tracking System. "
        + lang_instruction
        + "Be concise, helpful, and friendly. You may use Markdown and emojis. "
    )
    return base + context
