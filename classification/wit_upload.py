# -*- coding: utf-8 -*-
"""Загрузка обучающих данных ПрО «Древний Рим» в приложение Wit.ai.

Запуск (из корня репозитория nika, на хосте):
    docker compose exec -T problem-solver python3 /nika/kb/extra/section_subject_domain_of_ancient_rome/classification/wit_upload.py          # загрузка
    docker compose exec -T problem-solver python3 /nika/kb/extra/section_subject_domain_of_ancient_rome/classification/wit_upload.py status   # состояние обучения
    docker compose exec -T problem-solver python3 /nika/kb/extra/section_subject_domain_of_ancient_rome/classification/wit_upload.py test     # проверка распознавания

Токен берётся из /nika/nika.ini (секция [wit-ai], server_token) - в скрипте его нет.
В консоль выводится только ASCII, подробный журнал на русском - в _wit_upload.log рядом со скриптом.

Wit.ai, получая обучающую фразу, заводит размеченный фрагмент как НОВОЕ ключевое слово, если
не находит его среди ключевых слов сущности. Поэтому после загрузки фраз скрипт сверяет список
ключевых слов с эталонным и возвращает эталон: иначе вместо «Калигула» Wit.ai вернёт «Калигуле»,
и классификатор Ники не найдёт узел базы знаний. Поэтому в обучающих фразах сущность размечена
только в основной форме (ровно как ключевое слово), а падежные формы заданы синонимами - они
работают при распознавании вопроса, но не порождают новых ключевых слов при обучении.
"""
import configparser, io, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'wit_training_data.json')
LOG = os.path.join(HERE, '_wit_upload.log')
API, VER = 'https://api.wit.ai', '20240304'
OLD_PUBLIC_TOKEN = '7D4G3HK6UAKIXVVCW2I5TMRBLKJZVCGY'
BATCH = 50

log = io.open(LOG, 'a', encoding='utf-8')
def say(msg_ascii, detail=None):
    print(msg_ascii, flush=True)
    log.write(time.strftime('%H:%M:%S ') + (detail or msg_ascii) + '\n'); log.flush()

cfg = configparser.ConfigParser(interpolation=None)
cfg.read('/nika/nika.ini', encoding='utf-8')
TOKEN = cfg.get('wit-ai', 'server_token', fallback='').strip()
if not TOKEN or TOKEN == OLD_PUBLIC_TOKEN:
    say('ERROR: put YOUR Server Access Token into nika.ini ([wit-ai] server_token) first.')
    sys.exit(1)

def call(method, path, body=None, query=None, tok=None):
    q = {'v': VER}; q.update(query or {})
    q = {k: v for k, v in q.items() if v is not None}
    url = API + path + '?' + urllib.parse.urlencode(q)
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    for attempt in range(6):
        req = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': 'Bearer ' + (tok or TOKEN), 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read().decode('utf-8')
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8', 'replace')
            if e.code == 429:
                wait = 15 * (attempt + 1)
                say('  rate limited, waiting %ds' % wait); time.sleep(wait); continue
            return e.code, raw
        except Exception as e:          # URLError, ssl.SSLError, ConnectionResetError, timeout
            say('  network error: %s, retrying' % type(e).__name__, '  сетевая ошибка: %r' % e); time.sleep(5 * (attempt + 1))
    return 0, 'gave up after retries'

D = json.load(io.open(DATA, encoding='utf-8'))
ENT = D['entity']
KW = {k['keyword'] for k in ENT['keywords']}
TEXTS = {u['text'] for u in D['utterances']}

def entity_keywords():
    st, r = call('GET', '/entities/' + ENT['name'])
    return [k['keyword'] for k in (r.get('keywords') or [])] if st == 200 else None

def restore_keywords(tag):
    """Вернуть ровно эталонный список ключевых слов. Возвращает число удалённых лишних."""
    for attempt in range(6):
        have = entity_keywords() or []
        rogue = [k for k in have if k not in KW]
        missing = KW - set(have)
        if not rogue and not missing:
            say('%s: keywords OK (%d/%d, no auto-created)' % (tag, len(have), len(KW)))
            return 0
        say('%s: %d auto-created, %d missing -> restoring' % (tag, len(rogue), len(missing)),
            '%s: лишние ключевые слова: %s; недостающие: %s' % (tag, rogue, sorted(missing)))
        st, r = call('PUT', '/entities/' + ENT['name'], ENT)
        if st != 200:
            say('  PUT entity -> HTTP %s' % st, '  PUT entity -> %s %s' % (st, str(r)[:400]))
        time.sleep(15)
    say('%s: WARNING keywords still differ after retries, see _wit_upload.log' % tag)
    return -1

def app_info():
    st, r = call('GET', '/apps', query={'limit': 10, 'offset': 0})
    if st != 200 or not r: return None
    st, a = call('GET', '/apps/' + r[0]['id'])
    return a if st == 200 else r[0]

def status():
    a = app_info()
    if a:
        say('app=%s lang=%s training_status=%s last_trained_at=%s will_train_at=%s last_training_secs=%s' % (
            a.get('name'), a.get('lang'), a.get('training_status'), a.get('last_trained_at'),
            a.get('will_train_at'), a.get('last_training_duration_secs')))
        log.write('    app raw: ' + json.dumps(a, ensure_ascii=False)[:800] + '\n')
    have = entity_keywords()
    if have is not None:
        rogue = [k for k in have if k not in KW]
        say('entity %s: %d keywords stored, expected %d, auto-created %d' % (ENT['name'], len(have), len(KW), len(rogue)),
            'entity: %d ключевых слов, эталон %d, лишние: %s' % (len(have), len(KW), rogue[:60]))
    st, r = call('GET', '/intents')
    if st == 200: say('intents stored: %s' % ', '.join(sorted(x['name'] for x in r)))
    st, r = call('GET', '/utterances', query={'limit': 10000})
    if st == 200:
        c = Counter((u.get('intent') or {}).get('name', '-') for u in r)
        foreign = [u['text'] for u in r if u['text'] not in TEXTS]
        say('utterances stored: %d %s, not from our dataset: %d' % (len(r), dict(c), len(foreign)),
            'фразы не из наших данных: %s' % foreign)

def test():
    qs = ['Что такое консулат?', 'Кто такой Спартак?', 'Что такое римская магистратура?', 'Кто такие патриции?',
          'Что такое когорта?', 'Что такое Третья Сервильная война?', 'Что такое отношение побеждён?',
          'После кого правил Нерон?', 'Кем был побеждён Спартак?', 'Сколько человек насчитывал легион?',
          # падежные формы: проверяют синонимы при распознавании
          'Расскажи о Калигуле', 'Что ты знаешь о Нероне?', 'Расскажи о Цезаре', 'Кто правил до Нерона?',
          'Сколько человек было в легионе?', 'Расскажи про когорту']
    ok = 0
    for i, q in enumerate(qs):
        st, r = call('GET', '/message', query={'q': q})
        if st != 200:
            say('  HTTP %s' % st, '  %s -> HTTP %s %s' % (q, st, r)); continue
        intents = r.get('intents') or []
        intent = intents[0]['name'] if intents else '-'
        conf = intents[0]['confidence'] if intents else 0
        vals = [x.get('value') for x in (r.get('entities') or {}).get('rrel_entity:rrel_entity', [])]
        canon = [v for v in vals if v in KW]
        good = intent != '-' and len(vals) == 1 and len(canon) == 1
        ok += good
        say('  %s intent=%-24s conf=%.2f entities=%d canonical=%d' % ('OK ' if good else '-- ', intent, conf, len(vals), len(canon)),
            '  %s  %-40s intent=%-24s conf=%.2f  rrel_entity=%s' % ('OK ' if good else '-- ', q, intent, conf, vals))
        if i < 2: log.write('    raw: ' + json.dumps(r, ensure_ascii=False)[:1500] + '\n')
    say('TEST: %d/%d recognized, first 10 = trained phrasing, last 6 = case forms (details in _wit_upload.log)' % (ok, len(qs)))

def upload():
    st, r = call('GET', '/intents')
    if st != 200:
        say('ERROR: token rejected by Wit.ai (HTTP %s). Check server_token.' % st, 'GET /intents -> %s %s' % (st, r))
        sys.exit(1)
    have = {x['name'] for x in r}
    for name in D['intents']:
        if name in have: say('intent %s: exists' % name); continue
        st, r = call('POST', '/intents', {'name': name})
        say('intent %s: HTTP %s' % (name, st), 'intent %s: %s %s' % (name, st, r))

    # 1. удаляем фразы, которых нет в наших данных: именно они порождают лишние ключевые слова
    st, r = call('GET', '/utterances', query={'limit': 10000})
    stale = [u['text'] for u in (r if st == 200 else []) if u['text'] not in TEXTS]
    for i in range(0, len(stale), 100):
        st, r = call('DELETE', '/utterances', [{'text': t} for t in stale[i:i + 100]])
        say('stale utterances %d-%d deleted: HTTP %s' % (i + 1, min(i + 100, len(stale)), st),
            'удалены фразы: %s' % stale[i:i + 100])
    if not stale: say('stale utterances: none')
    time.sleep(10)

    # 2. сущность - строго эталонный список ключевых слов
    if entity_keywords() is None:
        st, r = call('POST', '/entities', ENT)
        say('entity created: HTTP %s' % st, 'POST entity -> %s %s' % (st, str(r)[:300]))
        time.sleep(10)
    restore_keywords('before utterances')

    # 3. обучающие фразы
    U = D['utterances']; sent = 0
    for i in range(0, len(U), BATCH):
        chunk = U[i:i + BATCH]
        st, r = call('POST', '/utterances', chunk)
        if st == 200:
            sent += len(chunk); say('utterances %d-%d: OK' % (i + 1, i + len(chunk)))
        else:
            say('utterances %d-%d: HTTP %s' % (i + 1, i + len(chunk), st),
                'utterances %d-%d -> %s %s' % (i + 1, i + len(chunk), st, str(r)[:600]))
        time.sleep(3)

    # 4. контроль: Wit.ai не должен был завести ни одного своего ключевого слова
    time.sleep(20)
    restore_keywords('after utterances')
    say('DONE: %d/%d utterances sent. Run "status" until training_status=done, then "test".' % (sent, len(U)))

def probe():
    """Проверка гипотезы: модель обучена, а пустые интенты даёт только определённая версия API."""
    qs = [('Что такое консулат?', 'trained'), ('Объясни мне, что такое претура', 'unseen')]
    versions = [None, '20200513', '20210928', '20220622', '20230215', '20240304', '20250101', '20260505']
    for q, kind in qs:
        for v in versions:
            st, r = call('GET', '/message', query={'q': q, 'v': v, 'n': 5})
            if st != 200:
                say('  %-7s v=%-8s HTTP %s' % (kind, v or 'none', st), '  %s v=%s -> %s %s' % (q, v, st, str(r)[:200]))
                continue
            it = r.get('intents') or []
            top = ('%s %.2f' % (it[0]['name'], it[0]['confidence'])) if it else '-'
            ents = sum(len(x) for x in (r.get('entities') or {}).values())
            say('  %-7s v=%-8s intents=%d top=%-26s entities=%d' % (kind, v or 'none', len(it), top, ents),
                '  %-35s v=%-8s intents=%s entities=%s' % (q, v or 'none', it, r.get('entities')))
    # интент с точки зрения API: сколько у него фраз
    st, r = call('GET', '/intents/about_entity')
    say('GET /intents/about_entity -> HTTP %s' % st, 'GET /intents/about_entity -> %s %s' % (st, str(r)[:500]))

def probe2():
    """Путь интерфейса и путь API различаются: проверяем клиентский токен и сохранённую версию."""
    Q = 'Объясни мне, что такое претура'
    def ask(label, **kw):
        st, r = call('GET', '/message', query=dict({'q': Q}, **kw.pop('query', {})), **kw)
        if st != 200:
            say('  %-28s HTTP %s' % (label, st), '  %s -> %s %s' % (label, st, str(r)[:300])); return
        it = r.get('intents') or []
        say('  %-28s intents=%d top=%s' % (label, len(it), ('%s %.2f' % (it[0]['name'], it[0]['confidence'])) if it else '-'),
            '  %s -> %s' % (label, json.dumps(r, ensure_ascii=False)[:600]))

    ask('server token')
    client = os.environ.get('WIT_CLIENT_TOKEN') or cfg.get('wit-ai', 'client_token', fallback='').strip()
    if client: ask('client token', tok=client)
    else: say('  client token: not provided (set client_token in nika.ini or WIT_CLIENT_TOKEN)')

    st, apps = call('GET', '/apps', query={'limit': 10, 'offset': 0})
    if st != 200 or not apps: say('  cannot list apps: HTTP %s' % st); return
    app = apps[0]['id']
    st, tags = call('GET', '/apps/%s/tags' % app)
    say('  existing versions: HTTP %s %s' % (st, [t.get('name') or t.get('tag') for t in (tags or [])] if st == 200 else ''),
        '  tags raw: %s' % str(tags)[:400])
    names = [t.get('name') or t.get('tag') for t in (tags or [])] if st == 200 else []
    if 'lr2' not in names:
        st, r = call('POST', '/apps/%s/tags' % app, {'tag': 'lr2'})
        say('  create version lr2: HTTP %s' % st, '  POST tag -> %s %s' % (st, str(r)[:300]))
        time.sleep(45)
    ask('version lr2 (tag)', query={'tag': 'lr2'})

mode = sys.argv[1] if len(sys.argv) > 1 else 'upload'
say('=== %s %s ===' % (mode.upper(), time.strftime('%Y-%m-%d %H:%M')))
{'status': status, 'test': test, 'upload': upload, 'probe': probe, 'probe2': probe2}.get(mode, upload)()
