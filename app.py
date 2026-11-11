import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime, date
from streamlit_gsheets import GSheetsConnection

# Настройка внешнего вида страницы
st.set_page_config(page_title="Расписание преподавателей", layout="wide")
st.title("📅 Расписание занятий")

# --- ПОДКЛЮЧЕНИЕ К GOOGLE ТАБЛИЦАМ ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- УПРАВЛЕНИЕ ПАРОЛЕМ ---
CONFIG_FILE = "config.json"


def load_admin_password():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("admin_password", "1234")
        except Exception:
            return "1234"
    return "1234"


def save_admin_password(new_pass):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"admin_password": new_pass}, f)


# --- ФУНКЦИИ ЗАГРУЗКИ ДАННЫХ ИЗ GOOGLE ---
def clean_df(df):
    """Очистка датафрейма от NaN и приведение к строкам"""
    return df.fillna("").astype(str).replace(["nan", "None", "<NA>"], "")


def load_schedule():
    df = conn.read(worksheet="Расписание", ttl=0)
    df = clean_df(df)
    if 'Запрос_отправлен' not in df.columns:
        df['Запрос_отправлен'] = ""
    return df


def load_teachers():
    try:
        df = conn.read(worksheet="Преподаватели", ttl=0)
        return clean_df(df)
    except Exception:
        return pd.DataFrame(columns=["ФИО", "Телефон", "Email"])


df = load_schedule()
if df.empty or 'Группа' not in df.columns:
    st.error("Не удалось загрузить расписание. Проверьте вкладку 'Расписание' в Google Таблице.")
    st.stop()

teachers_df = load_teachers()

# Техническая колонка для расчетов дат
df['Дата_dt'] = pd.to_datetime(df['Дата'], format='%d.%m.%Y', errors='coerce')
today = pd.to_datetime(date.today())
all_groups = sorted(df['Группа'].dropna().unique().tolist())
teacher_names_list = [name for name in teachers_df['ФИО'].tolist() if name.strip()]


# --- НАДЕЖНАЯ СИНХРОНИЗАЦИЯ ПРИВЯЗОК ---
def load_and_sync_mapping(current_groups):
    try:
        map_df = conn.read(worksheet="Привязка", ttl=0)
        map_df = clean_df(map_df)
    except Exception:
        map_df = pd.DataFrame(columns=["Группа", "Преподаватель"])

    if "Группа" not in map_df.columns:
        map_df = pd.DataFrame(columns=["Группа", "Преподаватель"])

    existing_links = dict(zip(map_df['Группа'], map_df['Преподаватель']))

    synced_data = []
    for g in current_groups:
        if g.strip():
            teacher = existing_links.get(g, "")
            synced_data.append({"Группа": g, "Преподаватель": teacher})

    synced_df = pd.DataFrame(synced_data)

    if not map_df.equals(synced_df):
        conn.update(worksheet="Привязка", data=synced_df)
        st.cache_data.clear()

    return synced_df


mapping_df = load_and_sync_mapping(all_groups)

# --- ГЛОБАЛЬНАЯ ПАНЕЛЬ НАПОМИНАНИЙ ---
new_modules_all = df[(df['Урок'] == '1') & (df['Запрос_отправлен'] != 'Да')]
alerts_all = []

for index, row in new_modules_all.iterrows():
    mod_date = row['Дата_dt']
    if pd.notnull(mod_date):
        days_until = (mod_date - today).days
        if 0 <= days_until <= 14:
            alerts_all.append({
                "group": row['Группа'],
                "date": mod_date.strftime('%d.%m.%Y'),
                "days": days_until,
                "module": row['Название модуля']
            })

alerts_all = sorted(alerts_all, key=lambda x: x['days'])
has_alerts = len(alerts_all) > 0

with st.expander(f"🔔 Напоминания: запросить доступы к модулям ({len(alerts_all)})", expanded=has_alerts):
    if has_alerts:
        for alert in alerts_all:
            days_text = "СЕГОДНЯ!" if alert['days'] == 0 else f"через {alert['days']} дней ({alert['date']})"
            st.warning(f"**{alert['group']}** — {days_text}\n\nМодуль: **«{alert['module']}»**")
    else:
        st.success("На ближайшие 2 недели неразобранных стартов новых модулей нет. Всё под контролем!")

# --- ОСНОВНОЙ ИНТЕРФЕЙС ДЛЯ ПРЕПОДАВАТЕЛЕЙ ---
st.divider()
st.subheader("👨‍🏫 Расписание вашей группы")

selected_teacher = st.selectbox("Кто вы?", ["(Показать все группы)"] + teacher_names_list)

if selected_teacher != "(Показать все группы)":
    teacher_groups = mapping_df[mapping_df['Преподаватель'].str.strip() == selected_teacher.strip()]['Группа'].tolist()
    teacher_groups = [g for g in teacher_groups if g in all_groups]

    if not teacher_groups:
        st.warning("За вами пока не закреплена ни одна группа. Обратитесь к администратору в Панель управления.")
        st.stop()

    selected_group = st.selectbox("Выберите вашу группу:", teacher_groups)
else:
    selected_group = st.selectbox("Выберите группу:", all_groups)

group_df = df[df['Группа'] == selected_group].copy()
group_df = group_df.sort_values(by='Дата_dt')
future_lessons = group_df[group_df['Дата_dt'] >= today]

if not future_lessons.empty:
    next_lesson = future_lessons.iloc[0]
    next_lesson_idx = next_lesson.name

    st.info(
        f"👉 **Ближайшее занятие: {next_lesson['Дата']}** | Урок {next_lesson['Урок']} | Модуль: «{next_lesson['Название модуля']}»")


    def highlight_next(row):
        return ['background-color: rgba(255, 215, 0, 0.3); font-weight: bold;'] * len(
            row) if row.name == next_lesson_idx else [''] * len(row)


    styled_df = group_df[['Дата', 'Название модуля', 'Урок']].style.apply(highlight_next, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
else:
    st.success("Ура! Программа для этой группы завершена.")
    st.dataframe(group_df[['Дата', 'Название модуля', 'Урок']], use_container_width=True, hide_index=True)

# --- ПАНЕЛЬ АДМИНИСТРАТОРА ---
st.divider()
st.subheader("⚙️ Панель администратора")

ADMIN_PIN = load_admin_password()
pin = st.text_input("Введите PIN-код:", type="password")

if pin == ADMIN_PIN:
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "✏️ Таблица", "➕ Вставить", "⏩ Сдвиг", "👨‍🏫 База и привязки", "✉️ Запрос доступов", "🔑 Смена пароля"
    ])

    # ВКЛАДКА 1: Таблица
    with tab1:
        st.info(
            "💡 Если вы удалите строку «Каникулы» (выделите слева и нажмите Delete), все последующие занятия этой группы автоматически сдвинутся обратно на неделю назад.")
        edit_df = df.drop(columns=['Дата_dt']).copy()
        edit_df['Дата'] = pd.to_datetime(edit_df['Дата'], format='%d.%m.%Y', errors='coerce').dt.date

        edited_df = st.data_editor(
            edit_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={"Дата": st.column_config.DateColumn("Дата", format="DD.MM.YYYY", required=True)}
        )
        if st.button("💾 Сохранить изменения таблицы", type="primary"):
            # 1. Ищем удаленные строки
            deleted_indices = set(edit_df.index) - set(edited_df.index)
            deleted_rows = edit_df.loc[list(deleted_indices)]
            holidays_deleted = deleted_rows[deleted_rows['Название модуля'].str.strip().str.lower() == 'каникулы']

            # 2. Подготавливаем финальный датафрейм
            final_df = edited_df.copy()
            final_df['tmp_dt'] = pd.to_datetime(final_df['Дата'], errors='coerce')

            # 3. Применяем автоматический обратный сдвиг
            if not holidays_deleted.empty:
                holidays_deleted['tmp_dt'] = pd.to_datetime(holidays_deleted['Дата'], errors='coerce')
                holidays_deleted = holidays_deleted.sort_values(by='tmp_dt', ascending=False)

                for _, hol in holidays_deleted.iterrows():
                    g = hol['Группа']
                    d = hol['tmp_dt']

                    if pd.notnull(d):
                        mask = (final_df['Группа'] == g) & (final_df['tmp_dt'] > d)
                        final_df.loc[mask, 'tmp_dt'] -= pd.Timedelta(weeks=1)

            # 4. Финализируем и сохраняем
            final_df['Дата'] = final_df['tmp_dt'].dt.strftime('%d.%m.%Y').fillna("")
            final_df = final_df.drop(columns=['tmp_dt'])

            conn.update(worksheet="Расписание", data=final_df)
            st.cache_data.clear()
            st.success("Сохранено в Google Таблицу! Если удалялись каникулы, применены обратные сдвиги.")
            st.rerun()

    # ВКЛАДКА 2: Вставка занятия
    with tab2:
        with st.form("insert_form"):
            ins_group = st.selectbox("В какую группу добавить?", all_groups)
            ins_date = st.date_input("Дата нового занятия", format="DD.MM.YYYY")
            ins_mod = st.text_input("Название модуля")
            ins_les = st.text_input("Номер урока")
            do_shift = st.checkbox("Сдвинуть последующие занятия на 1 неделю вперед?", value=True)
            submit_ins = st.form_submit_button("Подтвердить добавление")

            if submit_ins and ins_mod and ins_les:
                date_str = ins_date.strftime('%d.%m.%Y')
                temp_df = df.drop(columns=['Дата_dt']).copy()
                temp_df['tmp_dt'] = pd.to_datetime(temp_df['Дата'], format='%d.%m.%Y', errors='coerce')

                if do_shift:
                    mask = (temp_df['Группа'] == ins_group) & (
                                temp_df['tmp_dt'] >= pd.to_datetime(date_str, format='%d.%m.%Y'))
                    temp_df.loc[mask, 'tmp_dt'] += pd.Timedelta(days=7)
                    temp_df.loc[mask, 'Дата'] = temp_df.loc[mask, 'tmp_dt'].dt.strftime('%d.%m.%Y')

                new_row = pd.DataFrame(
                    [{'Группа': ins_group, 'Дата': date_str, 'Название модуля': ins_mod, 'Урок': ins_les,
                      'Запрос_отправлен': ''}])
                temp_df = temp_df.drop(columns=['tmp_dt'])
                temp_df = pd.concat([temp_df, new_row], ignore_index=True)

                temp_df['tmp_dt'] = pd.to_datetime(temp_df['Дата'], format='%d.%m.%Y', errors='coerce')
                temp_df = temp_df.sort_values(by=['Группа', 'tmp_dt'])

                final_df = temp_df.drop(columns=['tmp_dt'])
                conn.update(worksheet="Расписание", data=final_df)
                st.cache_data.clear()
                st.success("Добавлено в Google Таблицу!")
                st.rerun()

    # ВКЛАДКА 3: Сдвиг
    with tab3:
        with st.form("shift_form"):
            sh_group = st.selectbox("Группа для сдвига", all_groups)
            sh_date = st.date_input("С какой даты начинаются каникулы?", format="DD.MM.YYYY")
            sh_weeks = st.number_input("Сдвиг в неделях (сколько недель каникул):", value=1, min_value=1, max_value=10)

            if st.form_submit_button("Выполнить сдвиг и добавить Каникулы"):
                temp_df = df.drop(columns=['Дата_dt']).copy()
                temp_df['tmp_dt'] = pd.to_datetime(temp_df['Дата'], format='%d.%m.%Y', errors='coerce')
                target_dt = pd.to_datetime(sh_date.strftime('%d.%m.%Y'), format='%d.%m.%Y')

                if sh_weeks > 0:
                    # 1. Сдвигаем все будущие уроки вперед
                    mask = (temp_df['Группа'] == sh_group) & (temp_df['tmp_dt'] >= target_dt)
                    temp_df.loc[mask, 'tmp_dt'] += pd.Timedelta(weeks=sh_weeks)

                    # 2. Создаем строки-заглушки для каникул на освободившиеся даты
                    hol_rows = []
                    for i in range(int(sh_weeks)):
                        hol_dt = target_dt + pd.Timedelta(weeks=i)
                        hol_rows.append({
                            'Группа': sh_group,
                            'Дата': hol_dt.strftime('%d.%m.%Y'),
                            'Название модуля': 'Каникулы',
                            'Урок': '-',
                            'Запрос_отправлен': 'Да',
                            'tmp_dt': hol_dt
                        })

                    # 3. Вклеиваем каникулы в расписание
                    temp_df = pd.concat([temp_df, pd.DataFrame(hol_rows)], ignore_index=True)

                temp_df['Дата'] = temp_df['tmp_dt'].dt.strftime('%d.%m.%Y')
                temp_df = temp_df.sort_values(by=['Группа', 'tmp_dt'])

                final_df = temp_df.drop(columns=['tmp_dt'])
                conn.update(worksheet="Расписание", data=final_df)
                st.cache_data.clear()
                st.success("Строки «Каникулы» добавлены, а расписание успешно сдвинуто!")
                st.rerun()

    # ВКЛАДКА 4: Преподаватели
    with tab4:
        colA, colB = st.columns(2)
        with colA:
            st.write("**Контакты преподавателей**")
            edited_teachers = st.data_editor(teachers_df, num_rows="dynamic", use_container_width=True,
                                             key="edit_teachers_table")
            if st.button("💾 Сохранить контакты", type="primary"):
                conn.update(worksheet="Преподаватели", data=edited_teachers)
                st.cache_data.clear()
                st.success("Контакты сохранены!")
                st.rerun()

        with colB:
            st.write("**Закрепление за группами**")
            edited_mapping = st.data_editor(
                mapping_df,
                use_container_width=True,
                hide_index=True,
                key="edit_mapping_table",
                column_config={
                    "Группа": st.column_config.TextColumn("Группа", disabled=True),
                    "Преподаватель": st.column_config.SelectboxColumn("Преподаватель",
                                                                      options=[""] + teacher_names_list)
                }
            )
            if st.button("🔗 Сохранить привязки", type="primary"):
                conn.update(worksheet="Привязка", data=edited_mapping)
                st.cache_data.clear()
                st.success("Привязки успешно сохранены!")
                st.rerun()

    # ВКЛАДКА 5: Запрос доступов
    with tab5:
        if not alerts_all:
            st.success("🎉 Нет горящих модулей! Запрашивать и скрывать нечего.")
        else:
            alert_options = [f"{a['group']} — {a['module']}" for a in alerts_all]
            req_combined = st.selectbox("🎯 Выберите горящий модуль из списка:", alert_options)
            req_group, req_mod = req_combined.split(" — ", 1)

            st.divider()
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("✉️ Шаг 1: Сгенерировать")
                auto_teacher_match = mapping_df.loc[mapping_df['Группа'] == req_group, 'Преподаватель'].values
                auto_teacher = auto_teacher_match[0] if len(auto_teacher_match) > 0 and pd.notna(
                    auto_teacher_match[0]) else ""
                default_idx = teacher_names_list.index(auto_teacher) if auto_teacher in teacher_names_list else 0

                if not teacher_names_list:
                    st.error("Добавьте преподавателей во вкладке 'База и привязки'.")
                else:
                    req