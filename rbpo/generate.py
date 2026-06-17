# -*- coding: utf-8 -*-
r"""
Генератор русско-английского справочника лицензий SPDX.

Правила генерации:
- В website\<ID>.html вставляем блок: ВЕРДИКТ -> ПЕРЕВОД(RU) -> (ниже оригинал EN).
- Точка вставки: сразу после <div class="breadcrumb">...</div>.
- CSS — в <head> между RBPO-RU-STYLE-START/END; контент — между RBPO-RU-START/END.
- ИДЕМПОТЕНТНОСТЬ byte-for-byte: страница строится из неизменного снимка
  rbpo\pristine\<ID>.html.
- GATE (не публиковать черновики/неполные): публикуем ТОЛЬКО если
  translation_status == "verified" И пройдена fidelity (абзацев EN == RU).
  Если запись gate НЕ проходит, а страница уже была опубликована нами —
  СНИМАЕМ с публикации (возврат к pristine), чтобы страница и галочка совпадали.
- index.html: ✅ ставится ПО ФАКТУ — только тем страницам, где реально есть наш
  опубликованный блок (маркер RBPO-RU-START).

ТОЧНОСТЬ ПЕРЕВОДА — приоритет №1: перевод берётся ТОЛЬКО из
rbpo\translations\<ID>.md (дословный). Генератор НИЧЕГО не переводит сам.

Запуск:  py rbpo\generate.py [ID ...]   (без аргументов — все ID из verdicts.json)
"""
from __future__ import annotations
import json
import re
import sys
from html import escape
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"
VERDICTS = ROOT / "rbpo" / "verdicts.json"
TRANSLATIONS = ROOT / "rbpo" / "translations"
PRISTINE = ROOT / "rbpo" / "pristine"
DETAILS = ROOT / "json" / "details"
EXC = ROOT / "json" / "exceptions"

C_START, C_END = "<!-- RBPO-RU-START -->", "<!-- RBPO-RU-END -->"
S_START, S_END = "<!-- RBPO-RU-STYLE-START -->", "<!-- RBPO-RU-STYLE-END -->"
COL_MARK, CELL_MARK = "<!--RBPO-RU-COL-->", "<!--RBPO-RU-CELL-->"
# Маркеры панели фильтра/поиска на страницах-индексах (клиентский JS, статический хостинг).
F_CSS = ("<!-- RBPO-RU-FILTER-CSS-START -->", "<!-- RBPO-RU-FILTER-CSS-END -->")
F_BAR = ("<!-- RBPO-RU-FILTER-BAR-START -->", "<!-- RBPO-RU-FILTER-BAR-END -->")
F_JS = ("<!-- RBPO-RU-FILTER-JS-START -->", "<!-- RBPO-RU-FILTER-JS-END -->")

VERDICT = {
    "safe":    ("🟢", "БЕЗОПАСНО", "rbpo-safe"),
    "risk":    ("🟡", "РИСК", "rbpo-risk"),
    "unsafe":  ("🔴", "НЕБЕЗОПАСНО", "rbpo-unsafe"),
    "pending": ("⚪", "НЕ ОЦЕНЕНО", "rbpo-pending"),
}
CONF = {"high": "высокая", "medium": "средняя", "low": "низкая"}
PERM = {
    "commercial-use": "Коммерческое использование", "modifications": "Модификация",
    "distribution": "Распространение", "private-use": "Частное использование",
    "patent-use": "Использование патента",
    # эффект ИСКЛЮЧЕНИЙ (WITH-exception): что исключение дополнительно разрешает
    "linking-exception": "Связывание с независимыми модулями (copyleft не распространяется на них)",
    "output-exception": "Вывод/сгенерированный результат не покрывается copyleft",
    "embed-exception": "Встраивание в документ (документ не покрывается copyleft)",
    "gpl-compatibility": "Совместимость с GPL",
    "notice-relaxation": "Ослабление условий об уведомлениях (Apache §4) для встроенного объектного кода",
}
REQ = {
    "disclose-source": "Раскрытие исходного кода", "document-changes": "Документировать изменения",
    "include-copyright": "Указание авторства", "include-copyright--source": "Указание авторства (исходник)",
    "network-use-disclose": "Раскрытие при сетевом использовании", "same-license": "Та же лицензия",
    "same-license--file": "Та же лицензия (файл)", "same-license--library": "Та же лицензия (библиотека)",
    # спец-условия отдельных лицензий (raw-теги сверх словаря choosealicense):
    "advertising-clause": "Упоминание разработчика в рекламе (рекламная оговорка)",
    "rename-on-modify": "Переименование при модификации (шрифты)",
}
LIM = {
    "liability": "Ответственность", "warranty": "Гарантии",
    "trademark-use": "Использование товарных знаков", "patent-use": "Использование патента",
    # спец-ограничения отдельных лицензий:
    "no-standalone-font-sale": "Запрет продажи шрифта отдельно",
    "patent-retaliation": "Прекращение при патентном иске (ретрорсия)",
}

STYLE_CSS = """<style type="text/css">
.rbpo-ru{border:2px solid #888;border-radius:6px;padding:14px 18px;margin:18px 0;background:#fafafa;}
.rbpo-verdict{padding:8px 12px;border-radius:5px;margin-bottom:10px;}
.rbpo-badge{font-size:1.3em;font-weight:700;}
.rbpo-meta{color:#444;font-size:.9em;display:block;margin-top:4px;}
.rbpo-safe{background:#e6f4ea;border:1px solid #34a853;}
.rbpo-risk{background:#fef7e0;border:1px solid #f9ab00;}
.rbpo-unsafe{background:#fce8e6;border:1px solid #ea4335;}
.rbpo-pending{background:#eeeeee;border:1px solid #999999;}
.rbpo-tags div{margin:2px 0;}
.rbpo-justify{margin:10px 0;}
.rbpo-disclaimer{font-size:.85em;color:#555;font-style:italic;border-top:1px dashed #bbbbbb;padding-top:8px;margin-top:8px;}
.rbpo-translation{margin-top:14px;}
.rbpo-h2{color:#00416b;font-size:1.2em;}
.rbpo-prov{font-size:.85em;color:#666;font-weight:700;}
</style>"""

# --- Панель фильтра/поиска для index.html и exceptions-index.html ---
FILTER_CSS = """<style type="text/css">
.rbpo-filter{border:2px solid #4597cb;border-radius:6px;padding:10px 14px;margin:14px 0;background:#f0f7fc;font-size:.95em;}
.rbpo-filter .rbpo-row{display:flex;flex-wrap:wrap;gap:16px;align-items:center;}
.rbpo-filter label.rbpo-only{font-weight:700;color:#00416b;cursor:pointer;}
.rbpo-filter input[type="checkbox"]{transform:scale(1.2);margin-right:6px;vertical-align:middle;}
.rbpo-filter input.rbpo-q{padding:5px 9px;border:1px solid #99aabb;border-radius:4px;min-width:300px;font-size:1em;}
.rbpo-filter a.rbpo-reset{color:#00416b;}
.rbpo-filter .rbpo-count{color:#555;margin-left:auto;font-weight:700;}
.rbpo-filter .rbpo-hint{color:#666;font-size:.85em;margin-top:6px;}
.rbpo-unofficial{border:2px solid #8a6d3b;border-radius:6px;padding:10px 14px;margin:14px 0;background:#fff8e5;color:#4a3b19;font-size:.95em;}
.rbpo-unofficial a{color:#00416b;}
</style>"""

FILTER_BAR = """<div class="rbpo-unofficial" lang="ru">
  <strong>Неофициальная русскоязычная производная версия.</strong>
  Основана на SPDX License List Data 3.28.0. Этот сайт не является официальным
  ресурсом SPDX Workgroup или The Linux Foundation и не предполагает их одобрения.
  Официальный каталог: <a href="https://spdx.org/licenses/">spdx.org/licenses</a>.
</div>
<div class="rbpo-filter" lang="ru">
  <div class="rbpo-row">
    <label class="rbpo-only"><input type="checkbox" id="rbpo-only" /> Только переведённые на русский (<span id="rbpo-total">0</span>)</label>
    <input type="text" id="rbpo-q" class="rbpo-q" placeholder="Поиск по названию или SPDX-идентификатору…" />
    <a href="#" id="rbpo-reset" class="rbpo-reset">Показать все</a>
    <span class="rbpo-count">Показано: <span id="rbpo-shown">0</span></span>
  </div>
  <div class="rbpo-hint">✅ в колонке «Справка RU» — лицензия переведена на русский и снабжена предварительным вердиктом. Фильтр и поиск работают локально в браузере (хостинг не требует бэкенда).</div>
</div>"""

FILTER_JS = """<script type="text/javascript">
//<![CDATA[
(function(){
  function collect(){var all=document.getElementsByTagName('tr'),r=[];for(var i=0;i<all.length;i++){var tr=all[i];if(tr.querySelector&&tr.querySelector('td[about]'))r.push(tr);}return r;}
  var R=collect(),only=false,q='';
  function refresh(){var shown=0;for(var i=0;i<R.length;i++){var tr=R[i];var chk=tr.textContent.indexOf('\\u2705')>=0;var t=tr.textContent.toLowerCase();var ok=(!only||chk)&&(q===''||t.indexOf(q)>=0);tr.style.display=ok?'':'none';if(ok)shown++;}var s=document.getElementById('rbpo-shown');if(s)s.textContent=shown;}
  function init(){var total=0;for(var i=0;i<R.length;i++){if(R[i].textContent.indexOf('\\u2705')>=0)total++;}var tn=document.getElementById('rbpo-total');if(tn)tn.textContent=total;var cb=document.getElementById('rbpo-only');if(cb)cb.onchange=function(){only=cb.checked;refresh();};var qi=document.getElementById('rbpo-q');if(qi)qi.oninput=function(){q=qi.value.toLowerCase().replace(/^\\s+|\\s+$/g,'');refresh();};var rs=document.getElementById('rbpo-reset');if(rs)rs.onclick=function(){only=false;q='';if(cb)cb.checked=false;if(qi)qi.value='';refresh();return false;};refresh();}
  if(document.readyState!=='loading')init();else document.addEventListener('DOMContentLoaded',init);
})();
//]]>
</script>"""


def tags_line(values, mapping):
    items = [mapping.get(v, v) for v in (values or [])]
    return ", ".join(items) if items else "—"


def md_to_paragraphs(md_text: str) -> str:
    blocks = re.split(r"\n\s*\n", md_text.strip())
    out = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        if b.startswith("## "):
            out.append(f'<h3 class="rbpo-h2">{escape(b[3:].strip())}</h3>')
        else:
            out.append(f"<p>{escape(b)}</p>")
    return "\n      ".join(out)


def count_paragraphs(text: str) -> int:
    return len([b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()])


def en_paragraph_count(spdx_id: str):
    # лицензия (json\details, licenseText) ИЛИ исключение (json\exceptions, licenseExceptionText)
    for f, field in ((DETAILS / f"{spdx_id}.json", "licenseText"),
                     (EXC / f"{spdx_id}.json", "licenseExceptionText")):
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            txt = data.get(field, "")
            return count_paragraphs(txt) if txt else None
    return None


def fidelity_check(spdx_id: str, entry: dict, translation_md: str):
    """(ok, note). Проверяем баланс абзацев RU/EN, если нет явного override."""
    ru_n = count_paragraphs(translation_md)
    if entry.get("fidelity_override"):
        return True, f"fidelity_override: {entry.get('fidelity_note', '')}; RU={ru_n}"
    en_n = en_paragraph_count(spdx_id)
    if en_n is None:
        return False, "EN-эталон не найден (json\\details) и нет fidelity_override"
    return (en_n == ru_n), f"абзацев EN={en_n} RU={ru_n}"


def gate_ok(lid: str, entry: dict):
    """Можно ли публиковать страницу. (ok, reason)."""
    if entry.get("translation_status") != "verified":
        return False, f"translation_status={entry.get('translation_status')!r} (нужно 'verified')"
    tf = TRANSLATIONS / f"{lid}.md"
    if not tf.exists():
        return False, "нет файла перевода"
    if not (WEBSITE / f"{lid}.html").exists():
        return False, "нет страницы website"
    ok, note = fidelity_check(lid, entry, tf.read_text(encoding="utf-8"))
    if not ok:
        return False, f"fidelity НЕ пройдена ({note})"
    return True, note


def build_content(entry: dict, translation_md: str) -> str:
    v = entry["verdict"]
    emoji, label, css = VERDICT.get(v, VERDICT["pending"])
    conf = CONF.get(entry.get("confidence", ""), entry.get("confidence", "—"))
    source = entry.get("source", "auto")
    src_label = "предварительная оценка (черновик)"
    prov = "Неофициальный русский перевод. Официальным и обязательным остается оригинальный текст лицензии."
    disclaimer = ("Это неофициальная производная версия, не связанная с SPDX "
                  "Workgroup или The Linux Foundation и не предполагающая их "
                  "одобрения. Перевод и оценка носят справочный характер и не являются "
                  "юридической консультацией. При расхождении приоритет имеет "
                  "английский оригинал ниже.")
    if entry.get("source_conflict") or v == "pending":
        disclaimer = ("⚠ Оценка не завершена; требуется отдельная проверка условий лицензии. ") + disclaimer

    name_ru = entry.get("name_ru") or entry.get("name_full") or entry["spdx_id"]
    body = md_to_paragraphs(translation_md)
    perms = escape(tags_line(entry.get("permissions"), PERM))
    reqs = escape(tags_line(entry.get("requirements"), REQ))
    lims = escape(tags_line(entry.get("limitations"), LIM))

    return f"""{C_START}
<div class="rbpo-ru" lang="ru">
  <div class="rbpo-verdict {css}">
    <span class="rbpo-badge">Вердикт (черновик): {emoji} {escape(label)}</span>
    <span class="rbpo-meta">Уверенность: {escape(conf)} &#183; Copyleft: {escape(str(entry.get('copyleft_type','—')))} &#183; SPDX-ID: {escape(entry['spdx_id'])} &#183; {escape(src_label)}</span>
  </div>
  <div class="rbpo-tags">
    <div><strong>Разрешения:</strong> {perms}</div>
    <div><strong>Требования:</strong> {reqs}</div>
    <div><strong>Ограничения:</strong> {lims}</div>
  </div>
  <div class="rbpo-justify"><strong>Обоснование:</strong> {escape(entry.get('justification_ru','—'))}</div>
  <div class="rbpo-disclaimer">{escape(disclaimer)}</div>
  <div class="rbpo-translation">
    <h2 class="rbpo-h2">ПЕРЕВОД НА РУССКИЙ ЯЗЫК — {escape(name_ru)}</h2>
    <p class="rbpo-prov">{escape(prov)}</p>
      {body}
  </div>
</div>
{C_END}"""


def strip_markers(text: str) -> str:
    text = re.sub(re.escape(S_START) + r".*?" + re.escape(S_END), "", text, flags=re.S)
    text = re.sub(re.escape(C_START) + r".*?" + re.escape(C_END), "", text, flags=re.S)
    return text


def get_pristine(lid: str) -> str:
    pf = PRISTINE / f"{lid}.html"
    if pf.exists():
        return pf.read_text(encoding="utf-8")
    raw = (WEBSITE / f"{lid}.html").read_text(encoding="utf-8")
    had_markers = (C_START in raw) or (S_START in raw)
    src = strip_markers(raw)
    if had_markers:
        src = re.sub(r"\n(?:[ \t]*\n){2,}", "\n\n", src)
    PRISTINE.mkdir(parents=True, exist_ok=True)
    pf.write_text(src, encoding="utf-8")
    return src


def inject_page(pristine_html: str, content: str) -> str:
    html = pristine_html
    style_block = f"{S_START}\n{STYLE_CSS}\n{S_END}\n"
    if "</head>" not in html:
        raise RuntimeError("</head> не найден")
    html = html.replace("</head>", style_block + "</head>", 1)
    m = re.search(r'(<div class="breadcrumb">.*?</div>)', html, flags=re.S)
    if not m:
        raise RuntimeError("breadcrumb не найден")
    return html[:m.end()] + "\n" + content + html[m.end():]


def is_published(lid: str) -> bool:
    """ПО ФАКТУ: на странице есть наш опубликованный блок."""
    pg = WEBSITE / f"{lid}.html"
    return pg.exists() and (C_START in pg.read_text(encoding="utf-8"))


def published_ids(data: dict) -> set:
    return {lid for lid in data if is_published(lid)}


def is_exception_id(lid: str) -> bool:
    """ID — это исключение (LicenseException), а не лицензия."""
    return (EXC / f"{lid}.json").exists()


def update_index_file(path: Path, done_ids: set) -> None:
    """Добавляет колонку «Справка RU» + ✅-ячейки во ВСЕ таблицы файла-индекса.
    Работает и для index.html (лицензии: основная + Deprecated таблицы), и для
    exceptions-index.html (исключения: 1 таблица, 2 колонки). Точка крепления —
    атрибут about="./<id>.html" в строке (он одинаков в обоих индексах)."""
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    bak = path.parent / (path.name + ".orig")
    if not bak.exists():
        bak.write_text(text, encoding="utf-8")
    th = f'<th class="sorttable_nosort">{COL_MARK}Справка RU</th>'

    # 1) колонка-заголовок «Справка RU» в КАЖДУЮ таблицу файла.
    def add_header(hm):
        head = hm.group(0)
        return head if COL_MARK in head else head.replace("</tr></thead>", th + "</tr></thead>", 1)

    text = re.sub(r"<thead>.*?</thead>", add_header, text, flags=re.S)

    # 2) ✅-ячейка во ВСЕ строки во ВСЕХ таблицах (строго по факту done_ids)
    def repl(rowm):
        row = rowm.group(0)
        idm = re.search(r'about="\./([^"]+)\.html"', row)
        if not idm:
            return row  # строки без ссылки (в т.ч. заголовки) не трогаем
        lid = idm.group(1)
        mark = "✅" if lid in done_ids else ""
        cell = f'<td style="text-align:center">{CELL_MARK}{mark}</td>'
        if CELL_MARK in row:
            return re.sub(
                r'<td style="text-align:center">' + re.escape(CELL_MARK) + r".*?</td>",
                cell, row, flags=re.S,
            )
        return row.replace("</tr>", cell + "</tr>", 1)

    text = re.sub(r"<tr>.*?</tr>", repl, text, flags=re.S)
    path.write_text(text, encoding="utf-8")


def inject_index_filter(path: Path) -> None:
    """Идемпотентно вставляет панель фильтра/поиска (клиентский JS) в страницу-индекс:
    CSS → перед </head>, панель → перед первым <table>, JS → перед </body>.
    Повторный запуск сначала УДАЛЯЕТ старые marked-блоки, затем вставляет свежие."""
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    for s, e in (F_CSS, F_BAR, F_JS):
        text = re.sub(re.escape(s) + r".*?" + re.escape(e) + r"\n?", "", text, flags=re.S)
    if "</head>" in text:
        text = text.replace("</head>", f"{F_CSS[0]}\n{FILTER_CSS}\n{F_CSS[1]}\n</head>", 1)
    text = re.sub(r"<table", f"{F_BAR[0]}\n{FILTER_BAR}\n{F_BAR[1]}\n<table", text, count=1)
    js_block = f"{F_JS[0]}\n{FILTER_JS}\n{F_JS[1]}\n"
    if "</body>" in text:
        text = text.replace("</body>", js_block + "</body>", 1)
    else:
        text = text.replace("</html>", js_block + "</html>", 1)
    path.write_text(text, encoding="utf-8")


def main(argv):
    data = json.loads(VERDICTS.read_text(encoding="utf-8"))
    ids = argv or list(data.keys())
    for lid in ids:
        entry = data.get(lid)
        if not entry:
            print(f"[skip] {lid}: нет в verdicts.json")
            continue
        ok, reason = gate_ok(lid, entry)
        if ok:
            translation = (TRANSLATIONS / f"{lid}.md").read_text(encoding="utf-8")
            new_html = inject_page(get_pristine(lid), build_content(entry, translation))
            (WEBSITE / f"{lid}.html").write_text(new_html, encoding="utf-8")
            print(f"[ok]   {lid}: опубликовано (source={entry.get('source')}, verdict={entry.get('verdict')}, {reason})")
        else:
            # gate НЕ пройден: если страница была опубликована нами — снять (вернуть pristine)
            if is_published(lid):
                (WEBSITE / f"{lid}.html").write_text(get_pristine(lid), encoding="utf-8")
                print(f"[unpub] {lid}: снято с публикации — {reason}")
            else:
                print(f"[skip] {lid}: {reason}")

    done = published_ids(data)  # ✅ строго по факту наличия блока на странице
    lic_done = {x for x in done if not is_exception_id(x)}
    exc_done = {x for x in done if is_exception_id(x)}
    update_index_file(WEBSITE / "index.html", lic_done)              # лицензии
    update_index_file(WEBSITE / "exceptions-index.html", exc_done)   # исключения
    inject_index_filter(WEBSITE / "index.html")                      # панель фильтра/поиска
    inject_index_filter(WEBSITE / "exceptions-index.html")
    print(f"[index] ✅ лицензий: {len(lic_done)} · исключений: {len(exc_done)}")
    if exc_done:
        print(f"[exceptions] {', '.join(sorted(exc_done))}")


if __name__ == "__main__":
    main(sys.argv[1:])
