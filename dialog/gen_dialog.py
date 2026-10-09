# -*- coding: utf-8 -*-
"""ЛР 3. Генератор правил и фраз диалога для ПрО «Древний Рим».

Запуск из любого каталога:
    python3 kb/extra/section_subject_domain_of_ancient_rome/dialog/gen_dialog.py

Создаёт (перезаписывает) файлы:
  dialog/dialog_concepts.scs                  - классы сообщений ЛР 3, идентификаторы правил и
                                                классов фраз;
  SCg (.gwf):
  dialog/answer_rules/lr_answer_*.gwf        - универсальные правила ответа (одно правило на
                                                тип вопроса и состояние базы знаний, сущность -
                                                переменная);
  dialog/phrases/concept_phrase_*.gwf         - классы фраз ответа с шаблонами;
  classification/lr_classify_question/*.gwf   - правила классификации вопросов.

Почему правила классификации создаются для каждой сущности: машина логического вывода
(scl-machine) сравнивает текст сообщения со ссылкой шаблона только целиком
(TemplateSearcher::isContentIdentical), шаблонов вида «После кого правил <X>?» в ней нет.
Поэтому текст вопроса с конкретным именем задаётся данными (таблицы ниже), а правила
ответа от сущности не зависят.

Ограничение поиска по шаблону в sc-machine 0.8.0 (проверено на собранной NIKA): если в одном
шаблоне есть «одинаковые» тройки - от одной переменной две связки к узлам («_ruler _=> _years»,
«_ruler _=> _dynasty») или две дуги «lang_ru _-> _ссылка» - поиск находит лишние конструкции
(«до Нерона правила Третья Сервильная война»), теряет нужные (правило не срабатывает) или
зацикливается и роняет sc-server. Поэтому шаблоны строятся так, что у каждой переменной не
больше одной связки к узлу и одной к ссылке, а дуга lang_ru одна; check_equal_triples
проверяет это при каждом запуске.
"""
import os
import re
import sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
DOMAIN = os.path.dirname(HERE)  # .../section_subject_domain_of_ancient_rome
INSTANCES = os.path.join(DOMAIN, 'concepts', 'instances')
OUT_RULES = os.path.join(HERE, 'answer_rules')
OUT_PHRASES = os.path.join(HERE, 'phrases')
OUT_CLASSIFY = os.path.join(DOMAIN, 'classification', 'lr_classify_question')

# ----------------------------------------------------------------------------- данные
# Формы имён для вопросов: им. п., род. п., вин. п. (для одушевлённых совпадает с род.,
# кроме слов 1-го склонения), предл. п. и род (m/f/n/pl).
PERSONS = {
    # id: (им., род., вин.)
    'romulus': ('Ромул', 'Ромула', 'Ромула'),
    'numa_pompilius': ('Нума Помпилий', 'Нумы Помпилия', 'Нуму Помпилия'),
    'tarquinius_priscus': ('Луций Тарквиний Приск', 'Луция Тарквиния Приска', 'Луция Тарквиния Приска'),
    'servius_tullius': ('Сервий Туллий', 'Сервия Туллия', 'Сервия Туллия'),
    'tarquinius_superbus': ('Луций Тарквиний Гордый', 'Луция Тарквиния Гордого', 'Луция Тарквиния Гордого'),
    'augustus': ('Октавиан Август', 'Октавиана Августа', 'Октавиана Августа'),
    'tiberius': ('Тиберий', 'Тиберия', 'Тиберия'),
    'caligula': ('Калигула', 'Калигулы', 'Калигулу'),
    'claudius': ('Клавдий', 'Клавдия', 'Клавдия'),
    'nero': ('Нерон', 'Нерона', 'Нерона'),
    'gaius_julius_caesar': ('Гай Юлий Цезарь', 'Гая Юлия Цезаря', 'Гая Юлия Цезаря'),
    'marcus_licinius_crassus': ('Марк Лициний Красс', 'Марка Лициния Красса', 'Марка Лициния Красса'),
    'spartacus': ('Спартак', 'Спартака', 'Спартака'),
}
RULERS = ['romulus', 'numa_pompilius', 'tarquinius_priscus', 'servius_tullius', 'tarquinius_superbus',
          'augustus', 'tiberius', 'caligula', 'claudius', 'nero']
UNITS = {
    # id: (им., предл. с предлогом, род)
    'contubernium': ('контуберний', 'в контубернии', 'm'),
    'centuria_military': ('центурия', 'в центурии', 'f'),
    'manipulus': ('манипул', 'в манипуле', 'm'),
    'cohors': ('когорта', 'в когорте', 'f'),
    'cohors_prima': ('первая когорта', 'в первой когорте', 'f'),
    'legio': ('легион', 'в легионе', 'm'),
    'turma': ('турма', 'в турме', 'f'),
    'ala_cavalry': ('ала', 'в але', 'f'),
    'auxilia': ('ауксилии', 'в ауксилиях', 'pl'),
    'praetorian_guard': ('преторианская гвардия', 'в преторианской гвардии', 'f'),
}
OFFICES = {
    # id: (им., род., «занять …» / «стать …», род)
    'consulate': ('консулат', 'консулата', 'занять консулат', 'm'),
    'praetorship': ('претура', 'претуры', 'занять претуру', 'f'),
    'censorship': ('цензура', 'цензуры', 'занять цензуру', 'f'),
    'curule_aedileship': ('курульный эдилитет', 'курульного эдилитета', 'занять курульный эдилитет', 'm'),
    'quaestorship': ('квестура', 'квестуры', 'занять квестуру', 'f'),
    'plebeian_tribunate': ('народный трибунат', 'народного трибуната', 'занять народный трибунат', 'm'),
    'dictatorship': ('диктатура', 'диктатуры', 'занять диктатуру', 'f'),
    'magister_equitum': ('начальник конницы', 'начальника конницы', 'стать начальником конницы', 'm'),
    'interrex': ('интеррекс', 'интеррекса', 'стать интеррексом', 'm'),
}
PRIESTHOODS = {
    'pontifex_maximus': ('великий понтифик', 'm'),
    'flamen_quirinalis': ('фламин Квирина', 'm'),
}
VERB_END = {'m': '', 'f': 'а', 'n': 'о', 'pl': 'и'}

# ----------------------------------------------------------------------------- вопросы
# тип вопроса -> (класс сообщения, краткое имя, [(сущность, [шаблоны текста])])
def question_types():
    q = {}
    q['predecessor'] = ('concept_message_about_ruler_predecessor', [
        (e, ['После кого правил %s?' % PERSONS[e][0], 'Кто правил до %s?' % PERSONS[e][1]]) for e in RULERS])
    q['defeat'] = ('concept_message_about_defeat', [
        (e, ['Кем был побеждён %s?' % f[0], 'Кто победил %s?' % f[2]]) for e, f in PERSONS.items()])
    q['strength'] = ('concept_message_about_unit_strength', [
        (e, ['Сколько человек насчитывал%s %s?' % (VERB_END[g], nom), 'Сколько человек было %s?' % loc])
        for e, (nom, loc, g) in UNITS.items()])
    q['reign'] = ('concept_message_about_reign_years', [
        (e, ['Когда правил %s?' % PERSONS[e][0], 'В какие годы правил %s?' % PERSONS[e][0]]) for e in RULERS])
    period = [(e, ['К какому периоду относится %s?' % f[0], 'В какой период жил %s?' % f[0]])
              for e, f in PERSONS.items()]
    period += [(e, ['К какому периоду относится %s?' % f[0], 'В какой период существовал%s %s?' % (VERB_END[f[3]], f[0])])
               for e, f in OFFICES.items()]
    period += [(e, ['К какому периоду относится %s?' % f[0], 'В какой период существовал%s %s?' % (VERB_END[f[1]], f[0])])
               for e, f in PRIESTHOODS.items()]
    q['period'] = ('concept_message_about_period', period)
    q['minage'] = ('concept_message_about_minimum_age', [
        (e, ['С какого возраста можно было %s?' % f[2], 'Какой минимальный возраст для %s?' % f[1]])
        for e, f in OFFICES.items()])
    return q


def variants(text):
    """Варианты написания: с «?» и без, с заглавной и строчной буквы, с «ё» и «е»."""
    out = []
    base = [text, text.replace('ё', 'е')] if 'ё' in text else [text]
    for t in base:
        for tt in (t, t[:-1] if t.endswith('?') else t + '?'):
            for ttt in (tt, tt[0].lower() + tt[1:]):
                if ttt not in out:
                    out.append(ttt)
    return out

# ----------------------------------------------------------------------------- правила ответа
# Тройки посылки и шаблонов фраз:
#   ('in', класс, элемент)          - дуга принадлежности
#   ('rel', a, отношение, b)        - связка неролевого отношения a => b
# Имена с '_' - переменные; суффикс '~' - переменная-ссылка (sc-ссылка с текстом).
NAME = lambda v, p: [('rel', v, 'nrel_main_idtf', p + '~'), ('in', 'lang_ru', p + '~')]


def one_lang_ru(triples):
    """Оставляет в шаблоне фразы только одну дугу lang_ru -> ссылка (у имени основной сущности).

    Поиск по шаблону в sc-machine 0.8.0 обрабатывает одинаковые по виду тройки
    «lang_ru _-> _ссылка» группой и не проверяет для второй и следующих ссылок их связку
    nrel_main_idtf. Шаблон с двумя такими тройками находит не одну конструкцию, а тысячи
    (вторая ссылка - любая ссылка на русском языке), агент генерации фраз берёт первую
    найденную - отсюда ответ «до Нерона правила Третья Сервильная война». Шаблон с четырьмя
    такими тройками (фраза о поражении в конфликте) приводил к аварийному завершению sc-server.
    Проверено на собранной sc-machine 0.8.0: с одной дугой lang_ru каждый шаблон находит
    ровно одну конструкцию для каждой сущности.
    """
    out, seen = [], False
    for t in triples:
        if t[0] == 'in' and t[1] == 'lang_ru':
            if seen:
                continue
            seen = True
        out.append(t)
    return out

RULES = [
    # (id, приоритет, класс сообщения, переменная сущности, доп. тройки посылки,
    #  класс фраз, рус. идентификатор класса фраз, фразы, доп. тройки шаблона фраз)
    # «Что такое …?» / «Кто такой …?»: имя сущности, о которой спросили, подставляет переменная-
    # множество $set{_message} (основные идентификаторы элементов сообщения - это сущность,
    # связанная с ним ролью rrel_entity), потому что у одной переменной в шаблоне не может быть двух
    # дуг к ссылкам (имя и примечание) - см. check_equal_triples.
    ('lr_answer_about_ruler', 1, 'concept_message_about_entity', '_ruler',
     [('rel', '_ruler', 'nrel_reign_years', '_years'), ('rel', '_ruler', 'nrel_note', '_ar_ruler_note~')],
     'concept_phrase_about_ruler', 'фраза о правителе',
     ['$set{_message} - ${_ph_ruler_note}. Годы правления: ${_ph_ruler_years}',
      '$set{_message} (годы правления: ${_ph_ruler_years}) - ${_ph_ruler_note}.'],
     [('rel', '_ruler', 'nrel_note', '_ph_ruler_note~'), ('in', 'lang_ru', '_ph_ruler_note~'),
      ('rel', '_ruler', 'nrel_reign_years', '_years')] + NAME('_years', '_ph_ruler_years')),

    ('lr_answer_about_entity', 1, 'concept_message_about_entity', '_entity',
     [('in', 'concept_ancient_rome_dialog_entity', '_entity'), ('rel', '_entity', 'nrel_note', '_ae_note~')],
     'concept_phrase_about_rome_entity', 'фраза о сущности предметной области «Древний Рим»',
     ['$set{_message} - ${_ph_ae_note}.',
      'Справка из базы знаний: $set{_message} - ${_ph_ae_note}.'],
     [('rel', '_entity', 'nrel_note', '_ph_ae_note~'), ('in', 'lang_ru', '_ph_ae_note~')]),

    ('lr_answer_ruler_predecessor', 1, 'concept_message_about_ruler_predecessor', '_ruler',
     [('rel', '_ruler', 'nrel_ruler_predecessor', '_predecessor')],
     'concept_phrase_ruler_predecessor', 'фраза о предшественнике правителя',
     ['Перед тем как к власти пришёл ${_ph_pred_ruler}, правил ${_ph_pred_name}.',
      '${_ph_pred_name} правил непосредственно перед тем, как к власти пришёл ${_ph_pred_ruler}.'],
     NAME('_ruler', '_ph_pred_ruler') + [('rel', '_ruler', 'nrel_ruler_predecessor', '_predecessor')] + NAME('_predecessor', '_ph_pred_name')),

    ('lr_answer_dynasty_founder', 2, 'concept_message_about_ruler_predecessor', '_ruler',
     [('rel', '_ruler', 'nrel_ordinal_in_dynasty', 'number_1'), ('rel', '_ruler', 'nrel_dynasty_membership', '_dynasty')],
     'concept_phrase_dynasty_founder', 'фраза о первом правителе династии',
     ['${_ph_founder_name} стоит первым в правящей династии (${_ph_founder_dynasty}), поэтому предшественника в ней у него не было.',
      'Предшественника в династии нет: ${_ph_founder_name} - её первый правитель (${_ph_founder_dynasty}).'],
     NAME('_ruler', '_ph_founder_name') + [('rel', '_ruler', 'nrel_ordinal_in_dynasty', 'number_1'),
                                          ('rel', '_ruler', 'nrel_dynasty_membership', '_dynasty')] + NAME('_dynasty', '_ph_founder_dynasty')),

    ('lr_answer_ruler_predecessor_unknown', 3, 'concept_message_about_ruler_predecessor', '_ruler', [],
     'concept_phrase_ruler_predecessor_unknown', 'фраза о неизвестном предшественнике',
     ['О том, кто правил до того, как к власти пришёл ${_ph_nopred_ruler}, в базе знаний сведений нет.',
      'Предшественник для правителя «${_ph_nopred_ruler}» в базе знаний не указан.'],
     NAME('_ruler', '_ph_nopred_ruler')),

    ('lr_answer_defeat_in_conflict', 1, 'concept_message_about_defeat', '_person',
     [('rel', '_person', 'nrel_defeated_by', '_winner'), ('rel', '_conflict', 'nrel_conflict_leader', '_person')],
     'concept_phrase_defeat_in_conflict', 'фраза о поражении в вооружённом конфликте',
     ['${_ph_dc_person} возглавлял вооружённый конфликт «${_ph_dc_conflict}» и потерпел поражение; победителем стал ${_ph_dc_winner}.',
      'В конфликте «${_ph_dc_conflict}» победу одержал ${_ph_dc_winner}; побеждённой стороной руководил ${_ph_dc_person}.'],
     NAME('_person', '_ph_dc_person') + [('rel', '_person', 'nrel_defeated_by', '_winner')] + NAME('_winner', '_ph_dc_winner')
     + [('rel', '_conflict', 'nrel_conflict_leader', '_person')] + NAME('_conflict', '_ph_dc_conflict')),

    ('lr_answer_defeat', 2, 'concept_message_about_defeat', '_person',
     [('rel', '_person', 'nrel_defeated_by', '_winner')],
     'concept_phrase_defeat', 'фраза о поражении',
     ['${_ph_d_person} потерпел поражение; победитель - ${_ph_d_winner}.',
      'Победу над противником (${_ph_d_person}) одержал ${_ph_d_winner}.'],
     NAME('_person', '_ph_d_person') + [('rel', '_person', 'nrel_defeated_by', '_winner')] + NAME('_winner', '_ph_d_winner')),

    ('lr_answer_defeat_unknown', 3, 'concept_message_about_defeat', '_person', [],
     'concept_phrase_defeat_unknown', 'фраза об отсутствии сведений о поражении',
     ['В базе знаний нет сведений о том, что ${_ph_nd_person} потерпел поражение.',
      'Поражений, которые потерпел ${_ph_nd_person}, база знаний не описывает.'],
     NAME('_person', '_ph_nd_person')),

    # подразделение, в состав которого входят другие подразделения: связка nrel_unit_part
    # проходит от входящего подразделения (_subunit) к рассматриваемому (_unit)
    ('lr_answer_unit_strength_and_subunit', 1, 'concept_message_about_unit_strength', '_unit',
     [('rel', '_unit', 'nrel_unit_strength', '_strength'), ('rel', '_subunit', 'nrel_unit_part', '_unit')],
     'concept_phrase_unit_strength_and_subunit', 'фраза о численности и составе подразделения',
     ['Штатная численность подразделения «${_ph_usb_unit}» - ${_ph_usb_number} человек; в его состав входит подразделение «${_ph_usb_sub}».',
      'Подразделение «${_ph_usb_unit}» насчитывало ${_ph_usb_number} человек, в его состав входило подразделение «${_ph_usb_sub}».'],
     NAME('_unit', '_ph_usb_unit') + [('rel', '_unit', 'nrel_unit_strength', '_strength')] + NAME('_strength', '_ph_usb_number')
     + [('rel', '_subunit', 'nrel_unit_part', '_unit')] + NAME('_subunit', '_ph_usb_sub')),

    ('lr_answer_unit_strength', 2, 'concept_message_about_unit_strength', '_unit',
     [('rel', '_unit', 'nrel_unit_strength', '_strength')],
     'concept_phrase_unit_strength', 'фраза о численности подразделения',
     ['Штатная численность подразделения «${_ph_us_unit}» - ${_ph_us_number} человек.',
      'По штату подразделение «${_ph_us_unit}» насчитывало ${_ph_us_number} человек.'],
     NAME('_unit', '_ph_us_unit') + [('rel', '_unit', 'nrel_unit_strength', '_strength')] + NAME('_strength', '_ph_us_number')),

    ('lr_answer_unit_strength_unknown', 3, 'concept_message_about_unit_strength', '_unit', [],
     'concept_phrase_unit_strength_unknown', 'фраза о неизвестной численности подразделения',
     ['Численность подразделения «${_ph_nu_unit}» в базе знаний не указана.',
      'В базе знаний нет сведений о том, сколько человек насчитывало подразделение «${_ph_nu_unit}».'],
     NAME('_unit', '_ph_nu_unit')),

    # преемник правителя - тот, у кого рассматриваемый правитель указан как предшественник
    ('lr_answer_reign_and_successor', 1, 'concept_message_about_reign_years', '_ruler',
     [('rel', '_ruler', 'nrel_reign_years', '_years'), ('rel', '_successor', 'nrel_ruler_predecessor', '_ruler')],
     'concept_phrase_reign_and_successor', 'фраза о годах правления и преемнике правителя',
     ['${_ph_rs_ruler} правил в ${_ph_rs_years}; после него к власти пришёл ${_ph_rs_successor}.',
      '${_ph_rs_ruler} был у власти в ${_ph_rs_years}; его преемником стал ${_ph_rs_successor}.'],
     NAME('_ruler', '_ph_rs_ruler') + [('rel', '_ruler', 'nrel_reign_years', '_years')] + NAME('_years', '_ph_rs_years')
     + [('rel', '_successor', 'nrel_ruler_predecessor', '_ruler')] + NAME('_successor', '_ph_rs_successor')),

    ('lr_answer_reign', 2, 'concept_message_about_reign_years', '_ruler',
     [('rel', '_ruler', 'nrel_reign_years', '_years')],
     'concept_phrase_reign', 'фраза о годах правления',
     ['Согласно базе знаний, ${_ph_r_ruler} правил в ${_ph_r_years}',
      '${_ph_r_ruler} находился у власти в ${_ph_r_years}'],
     NAME('_ruler', '_ph_r_ruler') + [('rel', '_ruler', 'nrel_reign_years', '_years')] + NAME('_years', '_ph_r_years')),

    ('lr_answer_reign_unknown', 3, 'concept_message_about_reign_years', '_ruler', [],
     'concept_phrase_reign_unknown', 'фраза о неизвестных годах правления',
     ['Годы правления для правителя «${_ph_nr_ruler}» в базе знаний не указаны.',
      'В базе знаний нет сведений о том, когда правил ${_ph_nr_ruler}.'],
     NAME('_ruler', '_ph_nr_ruler')),

    ('lr_answer_person_period', 1, 'concept_message_about_period', '_entity',
     [('rel', '_entity', 'nrel_period_membership', '_period'), ('rel', '_period', 'nrel_period_years', '_years')],
     'concept_phrase_person_period', 'фраза о периоде, к которому относится лицо',
     ['${_ph_pp_entity} относится к периоду «${_ph_pp_period}» (${_ph_pp_years}).',
      '${_ph_pp_entity} жил в период «${_ph_pp_period}» (${_ph_pp_years}).'],
     NAME('_entity', '_ph_pp_entity') + [('rel', '_entity', 'nrel_period_membership', '_period')] + NAME('_period', '_ph_pp_period')
     + [('rel', '_period', 'nrel_period_years', '_years')] + NAME('_years', '_ph_pp_years')),

    ('lr_answer_office_period', 1, 'concept_message_about_period', '_entity',
     [('rel', '_entity', 'nrel_office_existence_period', '_period'), ('rel', '_period', 'nrel_period_years', '_years')],
     'concept_phrase_office_period', 'фраза о периоде существования должности',
     ['Должность «${_ph_op_entity}» существовала в период «${_ph_op_period}» (${_ph_op_years}).',
      'Период существования должности «${_ph_op_entity}» - ${_ph_op_period} (${_ph_op_years}).'],
     NAME('_entity', '_ph_op_entity') + [('rel', '_entity', 'nrel_office_existence_period', '_period')] + NAME('_period', '_ph_op_period')
     + [('rel', '_period', 'nrel_period_years', '_years')] + NAME('_years', '_ph_op_years')),

    ('lr_answer_period_unknown', 3, 'concept_message_about_period', '_entity', [],
     'concept_phrase_period_unknown', 'фраза о неизвестном периоде',
     ['В базе знаний не указано, к какому периоду относится «${_ph_np_entity}».',
      'Сведений о периоде для «${_ph_np_entity}» в базе знаний нет.'],
     NAME('_entity', '_ph_np_entity')),

    # предыдущая ступень cursus honorum - должность, для которой рассматриваемая указана следующей
    ('lr_answer_minimum_age_in_cursus', 1, 'concept_message_about_minimum_age', '_office',
     [('rel', '_office', 'nrel_office_minimum_age', '_age'), ('rel', '_prev_office', 'nrel_next_office_in_cursus_honorum', '_office')],
     'concept_phrase_minimum_age_in_cursus', 'фраза о минимальном возрасте и предыдущей ступени cursus honorum',
     ['Должность «${_ph_ac_office}» можно было занять не ранее ${_ph_ac_age} лет, пройдя перед этим должность «${_ph_ac_prev}».',
      'В cursus honorum должности «${_ph_ac_office}» предшествовала должность «${_ph_ac_prev}», а занять её разрешалось с ${_ph_ac_age} лет.'],
     NAME('_office', '_ph_ac_office') + [('rel', '_office', 'nrel_office_minimum_age', '_age')] + NAME('_age', '_ph_ac_age')
     + [('rel', '_prev_office', 'nrel_next_office_in_cursus_honorum', '_office')] + NAME('_prev_office', '_ph_ac_prev')),

    ('lr_answer_minimum_age', 2, 'concept_message_about_minimum_age', '_office',
     [('rel', '_office', 'nrel_office_minimum_age', '_age')],
     'concept_phrase_minimum_age', 'фраза о минимальном возрасте для должности',
     ['Должность «${_ph_a_office}» можно было занять не ранее ${_ph_a_age} лет.',
      'Занять должность «${_ph_a_office}» можно было с ${_ph_a_age} лет.'],
     NAME('_office', '_ph_a_office') + [('rel', '_office', 'nrel_office_minimum_age', '_age')] + NAME('_age', '_ph_a_age')),

    ('lr_answer_minimum_age_unknown', 3, 'concept_message_about_minimum_age', '_office', [],
     'concept_phrase_minimum_age_unknown', 'фраза о неизвестном минимальном возрасте',
     ['Минимальный возраст для должности «${_ph_na_office}» в базе знаний не указан.',
      'В базе знаний нет сведений о возрастном цензе для должности «${_ph_na_office}».'],
     NAME('_office', '_ph_na_office')),
]

RELATIONS = {'nrel_main_idtf', 'nrel_note', 'nrel_reign_years', 'nrel_ruler_predecessor', 'nrel_ordinal_in_dynasty',
             'nrel_dynasty_membership', 'nrel_defeated_by', 'nrel_conflict_leader', 'nrel_conflict_years',
             'nrel_unit_strength', 'nrel_unit_part', 'nrel_period_membership', 'nrel_office_existence_period',
             'nrel_period_years', 'nrel_office_minimum_age', 'nrel_office_collegiality', 'nrel_reply',
             'nrel_next_office_in_cursus_honorum', 'nrel_note',
             'nrel_implication', 'nrel_disjunction', 'nrel_answer_pattern', 'nrel_sc_text_translation',
             'nrel_phrase_template', 'nrel_inclusion'}
ROLES = {'rrel_entity', 'rrel_1', 'rrel_main_key_sc_element'}

# ----------------------------------------------------------------------------- GWF
class Gwf:
    """Минимальный писатель GWF 2.0 в формате редактора KBE."""

    def __init__(self):
        self.items = []
        self.n = 0
        self.const_nodes = {}

    def _id(self):
        self.n += 1
        return str(41000000 + self.n * 16)

    def node(self, idtf, *, var=False, kind=None, content=None, parent='0', x=0, y=0):
        if kind is None:
            if var:
                kind = 'general'
            elif idtf in RELATIONS:
                kind = 'relation'
            elif idtf in ROLES:
                kind = 'role'
            elif idtf.startswith('concept_') or idtf in ('lang_ru', 'atomic_logical_formula'):
                kind = 'group'
            else:
                kind = 'general'
        i = self._id()
        self.items.append(dict(tag='node', id=i, idtf=idtf, type='node/%s/perm/%s' % ('var' if var else 'const', kind),
                               content=content, parent=parent, x=x, y=y))
        return i

    def link(self, text, *, var=False, idtf='', parent='0', x=0, y=0):
        return self.node(idtf, var=var, kind='general', content=text, parent=parent, x=x, y=y)

    def contour(self, idtf=''):
        i = self._id()
        self.items.append(dict(tag='contour', id=i, idtf=idtf, points=[]))
        return i

    def pair(self, a, b, *, member=True, var=False, parent='0'):
        t = 'pair/%s/%s/perm/orient%s' % ('var' if var else 'const', 'pos' if member else '-', '/membership' if member else '')
        i = self._id()
        self.items.append(dict(tag='pair', id=i, type=t, a=a, b=b, parent=parent))
        return i

    def by_id(self):
        return {it['id']: it for it in self.items}

    def fit_contour(self, cid, pad=45):
        kids = [it for it in self.items if it['tag'] == 'node' and it['parent'] == cid]
        xs = [k['x'] for k in kids] or [0]
        ys = [k['y'] for k in kids] or [0]
        l, r, t, b = min(xs) - pad, max(xs) + pad + 120, min(ys) - pad, max(ys) + pad
        c = self.by_id()[cid]
        c['points'] = [(l, t), (r, t), (r, b), (l, b)]

    def xml(self):
        idx = self.by_id()

        def xy(i, depth=0):
            it = idx[i]
            if it['tag'] == 'node':
                return it['x'], it['y']
            if it['tag'] == 'contour':
                p = it['points'] or [(0, 0)]
                return sum(q[0] for q in p) / len(p), sum(q[1] for q in p) / len(p)
            if depth > 5:
                return 0, 0
            ax, ay = xy(it['a'], depth + 1)
            bx, by = xy(it['b'], depth + 1)
            return (ax + bx) / 2, (ay + by) / 2

        out = ['<?xml version="1.0" encoding="UTF-8"?>', '<GWF version="2.0">', '    <staticSector>']
        for it in self.items:
            if it['tag'] == 'node':
                w = max(20, 8 * len(it['idtf'] or ' '))
                out.append('        <node type="%s" idtf="%s" shapeColor="0" id="%s" parent="%s" left="0" top="0" '
                           'right="%d" bottom="23" textColor="164" text_angle="0" text_font="Times New Roman" '
                           'font_size="10" x="%.1f" y="%.1f" haveBus="false" idtf_pos="0">'
                           % (it['type'], escape(it['idtf'], {'"': '&quot;'}), it['id'], it['parent'], w, it['x'], it['y']))
                if it['content'] is not None:
                    out.append('            <content type="1" mime_type="content/term" content_visibility="true" '
                               'file_name=""><![CDATA[%s]]></content>' % (it['content'] or ' '))
                else:
                    out.append('            <content type="0" mime_type="" content_visibility="false" file_name=""/>')
                out.append('        </node>')
            elif it['tag'] == 'pair':
                bx, by = xy(it['a'])
                ex, ey = xy(it['b'])
                out.append('        <pair type="%s" idtf="" shapeColor="0" id="%s" parent="%s" id_b="%s" id_e="%s" '
                           'b_x="%.1f" b_y="%.1f" e_x="%.1f" e_y="%.1f" dotBBalance="0" dotEBalance="0">'
                           % (it['type'], it['id'], it['parent'], it['a'], it['b'], bx, by, ex, ey))
                out.append('            <points/>')
                out.append('        </pair>')
        for it in self.items:
            if it['tag'] == 'contour':
                # Как пишет сам KBE: у безымянного контура нет атрибутов подписи. KBE 0.4.x при ненулевом
                # idtf_pos_x/idtf_pos_y ставит подпись даже пустому идентификатору и падает (null mTextItem).
                # Позиция подписи задаётся относительно центра контура, а не в координатах сцены.
                if it['idtf']:
                    cx, cy = xy(it['id'])
                    l, t = it['points'][0]
                    out.append('        <contour type="contour/const/perm" idtf="%s" shapeColor="0" id="%s" parent="0" '
                               'left="0" top="0" right="%d" bottom="23" textColor="164" text_angle="0" '
                               'text_font="Times New Roman" font_size="10" idtf_pos_x="%d" idtf_pos_y="%d">'
                               % (escape(it['idtf']), it['id'], 8 * len(it['idtf']), l - cx + 10, t - cy - 28))
                else:
                    out.append('        <contour type="contour/const/perm" idtf="" shapeColor="0" id="%s" parent="0">'
                               % it['id'])
                out.append('            <points>')
                for (px, py) in it['points']:
                    out.append('                <point x="%.1f" y="%.1f"/>' % (px, py))
                out.append('            </points>')
                out.append('        </contour>')
        out += ['    </staticSector>', '</GWF>']
        return '\n'.join(out) + '\n'

    def save(self, path):
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(self.xml())


class Scope:
    """Элементы внутри одного контура: одинаковые имена - один sc-элемент."""

    def __init__(self, g, cid, x0, y0, cols=3, dx=230, dy=95):
        self.g, self.cid, self.x0, self.y0, self.cols, self.dx, self.dy = g, cid, x0, y0, cols, dx, dy
        self.names = {}

    def el(self, name):
        if name not in self.names:
            k = len(self.names)
            x = self.x0 + (k % self.cols) * self.dx
            y = self.y0 + (k // self.cols) * self.dy
            var = name.startswith('_')
            if name.endswith('~'):
                self.names[name] = self.g.link(' ', var=True, idtf=name[:-1], parent=self.cid, x=x, y=y)
            else:
                self.names[name] = self.g.node(name, var=var, parent=self.cid, x=x, y=y)
        return self.names[name]

    def add(self, triple):
        if triple[0] == 'in':
            _, cls, elem = triple
            return self.g.pair(self.el(cls), self.el(elem), member=True, var=True, parent=self.cid)
        _, a, rel, b = triple
        arc = self.g.pair(self.el(a), self.el(b), member=False, var=True, parent=self.cid)
        self.g.pair(self.el(rel), arc, member=True, var=True, parent=self.cid)
        return arc

    def role(self, role, a, b):
        m = self.g.pair(self.el(a), self.el(b), member=True, var=True, parent=self.cid)
        self.g.pair(self.el(role), m, member=True, var=True, parent=self.cid)
        return m

# ----------------------------------------------------------------------------- построение файлов
def build_answer_rule(spec):
    rid, prio, mclass, ent, extra, pclass = spec[:6]
    g = Gwf()
    top = {}

    def tnode(name, x, y):
        top[name] = g.node(name, x=x, y=y)
        return top[name]

    rule = tnode(rid, 120, 60)
    tnode('concept_answer_on_standard_message_rule', 120, 0)
    tnode('concept_answer_on_standard_message_rule_priority_%d' % prio, 470, 0)
    g.pair(top['concept_answer_on_standard_message_rule'], rule)
    g.pair(top['concept_answer_on_standard_message_rule_priority_%d' % prio], rule)
    # посылка
    c_if = g.contour()
    s = Scope(g, c_if, 80, 260)
    s.add(('in', 'concept_message', '_message'))
    s.add(('in', mclass, '_message'))
    s.role('rrel_entity', '_message', ent)
    for t in extra:
        s.add(t)
    g.fit_contour(c_if)
    # следствие
    c_then = g.contour()
    s2 = Scope(g, c_then, 860, 260, cols=2)
    arc = s2.add(('rel', '_message', 'nrel_reply', '_reply_message'))
    s2.add(('in', 'concept_atomic_message', '_reply_message'))
    s2.add(('in', mclass, '_reply_message'))
    g.fit_contour(c_then)
    impl = g.pair(c_if, c_then, member=False)
    tnode('nrel_implication', 600, 160)
    g.pair(top['nrel_implication'], impl)
    m = g.pair(rule, impl)
    tnode('rrel_main_key_sc_element', 360, 160)
    g.pair(top['rrel_main_key_sc_element'], m)
    tnode('atomic_logical_formula', 600, 120)
    g.pair(top['atomic_logical_formula'], c_if)
    g.pair(top['atomic_logical_formula'], c_then)
    # шаблон ответа
    tup = g.node('', kind='tuple', x=820, y=60)
    tnode('nrel_answer_pattern', 820, 0)
    tnode(pclass, 1120, 60)
    tnode('rrel_1', 1120, 0)
    pat = g.pair(rule, tup, member=False)
    g.pair(top['nrel_answer_pattern'], pat)
    m1 = g.pair(tup, top[pclass])
    g.pair(top['rrel_1'], m1)
    return g


def build_phrase_class(spec):
    rid, prio, mclass, ent, extra, pclass, pidtf, phrases, ttriples = spec
    g = Gwf()
    cls = g.node(pclass, x=120, y=60)
    sup = g.node('concept_phrase', x=120, y=0)
    lang = g.node('lang_ru', x=420, y=0)
    inc = g.pair(sup, cls, member=False)
    g.pair(g.node('nrel_inclusion', x=300, y=40), inc)
    tmpl_rel = g.node('nrel_phrase_template', x=420, y=120)
    # один шаблон (контур) на все фразы класса: переменные-ссылки объявляются один раз
    c = g.contour()
    s = Scope(g, c, 620, 260)
    s.add(('in', 'concept_message', '_message'))
    s.role('rrel_entity', '_message', ent)
    for t in one_lang_ru(ttriples):
        s.add(t)
    g.fit_contour(c)
    for k, text in enumerate(phrases):
        ph = g.link(text, x=120, y=260 + k * 160)
        g.pair(cls, ph)
        g.pair(lang, ph)
        arc = g.pair(ph, c, member=False)
        g.pair(tmpl_rel, arc)
        # проверка: все переменные текста объявлены в шаблоне
        for v in re.findall(r'\$\{(_\w+)\}', text):
            assert v + '~' in s.names, (pclass, v)
    return g


def build_classify_rule(qtype, mclass, entity, templates):
    rid = 'lr_classify_%s_%s_message' % (qtype, entity)
    g = Gwf()
    rule = g.node(rid, x=120, y=40)
    g.pair(g.node('concept_classify_message_rule_priority_1', x=120, y=-20), rule)
    tup = g.node('', kind='tuple', x=420, y=120)
    g.pair(g.node('nrel_disjunction', x=420, y=60), tup)
    alf = g.node('atomic_logical_formula', x=760, y=40)
    twl = g.node('concept_template_with_links', x=760, y=100)
    texts = []
    for t in templates:
        texts += variants(t)
    for k, text in enumerate(texts):
        col, row = k % 2, k // 2
        c = g.contour('if_%s_%s_%d' % (qtype, entity, k + 1))
        x0, y0 = 80 + col * 720, 260 + row * 260
        tr = g.node('', var=True, parent=c, x=x0 + 230, y=y0)
        msg = g.node('_message', var=True, parent=c, x=x0, y=y0)
        cm = g.node('concept_message', parent=c, x=x0, y=y0 + 90)
        rel = g.node('nrel_sc_text_translation', parent=c, x=x0 + 230, y=y0 + 90)
        ln = g.link(text, var=True, idtf='_q_%s_%s_%d' % (qtype, entity, k + 1), parent=c, x=x0 + 460, y=y0)
        g.pair(cm, msg, var=True, parent=c)
        a = g.pair(tr, msg, member=False, var=True, parent=c)
        g.pair(rel, a, var=True, parent=c)
        g.pair(tr, ln, var=True, parent=c)
        g.fit_contour(c)
        g.pair(tup, c)
        g.pair(alf, c)
        g.pair(twl, c)
    c_then = g.contour()
    y0 = 260 + ((len(texts) + 1) // 2) * 260
    msg = g.node('_message', var=True, parent=c_then, x=300, y=y0)
    cls = g.node(mclass, parent=c_then, x=300, y=y0 + 90)
    ent = g.node(entity, parent=c_then, x=640, y=y0)
    role = g.node('rrel_entity', parent=c_then, x=640, y=y0 + 90)
    g.pair(cls, msg, var=True, parent=c_then)
    m = g.pair(msg, ent, var=True, parent=c_then)
    g.pair(role, m, var=True, parent=c_then)
    g.fit_contour(c_then)
    g.pair(alf, c_then)
    impl = g.pair(tup, c_then, member=False)
    g.pair(g.node('nrel_implication', x=1100, y=120), impl)
    mm = g.pair(rule, impl)
    g.pair(g.node('rrel_main_key_sc_element', x=1100, y=40), mm)
    return rid, g, texts


NEW_MESSAGE_CLASSES = [
    ('concept_message_about_reign_years', 'сообщение о годах правления',
     'Сообщение о годах правления - атомарное сообщение, в котором спрашивается, когда правил указанный правитель Древнего Рима.'),
    ('concept_message_about_period', 'сообщение о периоде истории',
     'Сообщение о периоде истории - атомарное сообщение, в котором спрашивается, к какому периоду истории Древнего Рима относится указанное лицо или должность.'),
    ('concept_message_about_minimum_age', 'сообщение о минимальном возрасте для должности',
     'Сообщение о минимальном возрасте для должности - атомарное сообщение, в котором спрашивается, с какого возраста можно было занять указанную римскую должность.'),
]


def write_concepts(path):
    """Классы сообщений ЛР 3 и русские идентификаторы правил и классов фраз."""
    out = ['/* Файл создан gen_dialog.py. Классы сообщений, добавленные в ЛР 3,',
           '   и идентификаторы правил ответа и классов фраз. */', '']
    for cid, name, definition in NEW_MESSAGE_CLASSES:
        out += [cid, '<- sc_node_class;', '=> nrel_main_idtf:', '    [%s]' % name, '    (* <- lang_ru;; *);',
                '<= nrel_inclusion: concept_atomic_message;', '<- rrel_key_sc_element:', '    ...', '    (*',
                '    => nrel_main_idtf:', '        [Опр. (%s)]' % name, '        (* <- lang_ru;; *);;',
                '    <- definition;;', '    <= nrel_sc_text_translation:', '        ...', '        (*',
                '        -> rrel_example:', '            [%s]' % definition, '            (* <- lang_ru;; *);;',
                '        *);;', '    <= nrel_using_constants: {', '        concept_atomic_message;',
                '        rrel_entity', '    };;', '    *);;', '']
    ents = dialog_entities()
    out += ['concept_ancient_rome_dialog_entity', '<- sc_node_class;', '=> nrel_main_idtf:',
            '    [сущность предметной области «Древний Рим», о которой можно спросить «Что такое …?»]',
            '    (* <- lang_ru;; *);',
            '=> nrel_note:',
            '    [Сущности предметной области «Древний Рим», для которых есть правила классификации вопросов «Что такое …?»'
            ' и «Кто такой …?», кроме правителей: о правителе Ника отвечает по отдельному правилу,'
            ' добавляя годы правления]',
            '    (* <- lang_ru;; *);']
    out += ['-> %s;' % e for e in ents[:-1]] + ['-> %s;;' % ents[-1], '']
    for spec in RULES:
        rid, prio, pclass, pidtf = spec[0], spec[1], spec[5], spec[6]
        rule_name = pidtf.replace('фраза', 'правило ответа', 1)
        out += ['%s' % rid, '=> nrel_main_idtf:', '    [%s (приоритет %d)]' % (rule_name, prio),
                '    (* <- lang_ru;; *);;', '']
        out += ['%s' % pclass, '<- sc_node_class;', '=> nrel_main_idtf:', '    [%s]' % pidtf,
                '    (* <- lang_ru;; *);;', '']
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out))

# ----------------------------------------------------------------------------- проверки и запуск
CLASSIFY_ENTITY = os.path.join(DOMAIN, 'classification', 'lr_classify_entity')


def dialog_entities():
    """Сущности ЛР 2 с правилами «Что такое …?» (по именам файлов), кроме правителей."""
    ents = sorted(fn[len('lr_classify_'):-len('.gwf')] for fn in os.listdir(CLASSIFY_ENTITY)
                  if fn.startswith('lr_classify_') and fn.endswith('.gwf'))
    return [e for e in ents if e not in RULERS]


def _kind(x):
    if x.endswith('~'):
        return 'link'
    if x.startswith('_') and x != '_message':
        return 'node'
    return 'const:' + x          # _message при поиске уже связана с сообщением, как константа


def check_equal_triples(triples, where):
    """Запрещает в одном шаблоне «одинаковые» тройки в смысле поиска sc-machine 0.8.0.

    Тройки считаются одинаковыми (ScTemplateSearch::IsTriplesEqual), если у них один и тот же
    начальный элемент (или один и тот же конечный) и совпадают типы остальных элементов,
    например «_ruler _=> _years» и «_ruler _=> _dynasty» или «lang_ru _-> _ссылка1» и
    «lang_ru _-> _ссылка2». Такие тройки поиск сопоставляет дугам группой и при некоторых
    порядках дуг в памяти теряет решения или находит лишние: правило «годы правления и династия»
    не срабатывало ни для одного императора, шаблон с двумя дугами lang_ru давал тысячи
    результатов. Поэтому у каждой переменной в шаблоне не больше одной исходящей связки к узлу и
    одной к ссылке, а связи с другими сущностями проходят через другие переменные.
    """
    edges = []
    for t in triples:
        if t[0] == 'in':
            edges.append(('access', t[1], t[2]))
        elif t[0] == 'role':
            edges.append(('access', t[1], t[3]))
        else:
            edges.append(('common', t[1], t[3]))
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            (e1, a1, b1), (e2, a2, b2) = edges[i], edges[j]
            if e1 != e2:
                continue
            same_src = a1 == a2 and _kind(b1) == _kind(b2) and not _kind(b1).startswith('const:')
            same_trg = b1 == b2 and _kind(a1) == _kind(a2) and not _kind(a1).startswith('const:')
            dup = (a1, b1) == (a2, b2)
            assert not (same_src or same_trg or dup), ('одинаковые тройки', where, edges[i], edges[j])


def answer_premise(spec):
    rid, prio, mclass, ent, extra = spec[:5]
    return [('in', 'concept_message', '_message'), ('in', mclass, '_message'),
            ('role', '_message', 'rrel_entity', ent)] + list(extra)


def phrase_template(spec):
    ent, ttriples = spec[3], spec[8]
    return [('in', 'concept_message', '_message'), ('role', '_message', 'rrel_entity', ent)] + one_lang_ru(ttriples)

def kb_main_idtfs():
    """id -> основной идентификатор из файлов экземпляров (для сверки таблиц)."""
    res = {}
    for fn in os.listdir(INSTANCES):
        if not fn.endswith('.scs'):
            continue
        cur = None
        for line in open(os.path.join(INSTANCES, fn), encoding='utf-8'):
            m = re.match(r'^([a-z][a-z0-9_]*)\b', line)
            if m:
                cur = m.group(1)
            m = re.search(r'nrel_main_idtf: \[([^\]]+)\]', line)
            if m and cur and cur not in res:
                res[cur] = m.group(1)
    return res


def main():
    idtfs = kb_main_idtfs()
    errors = []
    for e, f in PERSONS.items():
        if idtfs.get(e) != f[0]:
            errors.append('%s: %r != %r' % (e, idtfs.get(e), f[0]))
    for table in (UNITS, OFFICES, PRIESTHOODS):
        for e, f in table.items():
            if idtfs.get(e) != f[0]:
                errors.append('%s: %r != %r' % (e, idtfs.get(e), f[0]))
    if errors:
        sys.exit('Таблица имён не совпадает с базой знаний:\n' + '\n'.join(errors))

    for d in (OUT_RULES, OUT_PHRASES, OUT_CLASSIFY):
        os.makedirs(d, exist_ok=True)
    texts_seen = {}
    n_rules = n_phrases = n_cls = 0
    for spec in RULES:
        check_equal_triples(answer_premise(spec), spec[0])
        check_equal_triples(phrase_template(spec), spec[5])
        build_answer_rule(spec).save(os.path.join(OUT_RULES, spec[0] + '.gwf'))
        n_rules += 1
    seen_phrases = set()
    for spec in RULES:
        for p in spec[7]:
            assert p not in seen_phrases, p
            seen_phrases.add(p)
        build_phrase_class(spec).save(os.path.join(OUT_PHRASES, spec[5] + '.gwf'))
        n_phrases += len(spec[7])
    for qtype, (mclass, items) in question_types().items():
        for entity, templates in items:
            rid, g, texts = build_classify_rule(qtype, mclass, entity, templates)
            for t in texts:
                assert t not in texts_seen, (t, texts_seen.get(t), rid)
                texts_seen[t] = rid
            g.save(os.path.join(OUT_CLASSIFY, 'lr_classify_%s_%s.gwf' % (qtype, entity)))
            n_cls += 1
    write_concepts(os.path.join(HERE, 'dialog_concepts.scs'))
    print('answer rules: %d, phrase classes: %d (phrases: %d), classification rules: %d (texts: %d)'
          % (n_rules, len(RULES), n_phrases, n_cls, len(texts_seen)))


if __name__ == '__main__':
    main()
