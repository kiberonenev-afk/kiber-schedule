import streamlit as st
import pandas as pd
import os
import shutil
import json
from datetime import datetime, date

# Настройка внешнего вида страницы
st.set_page_config(page_title="Расписание преподавателей", layout="wide")
st.title("📅 Расписание занятий")

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


# --- ФУНКЦИЯ СОЗДАНИЯ БЭКАПОВ ---
def make_backup(filename):
    if os.path.exists(filename):
        os.makedirs("backups", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(filename, f"backups/{timestamp}_{filename}")


# --- ФУНКЦИИ ЗАГРУЗКИ ДАННЫХ ---
def load_schedule():
    df = pd.read_csv("Расписание_Средняя_группа_2026.csv", dtype=str)
    if 'Запрос_отправлен' not in df.columns:
        df['Запрос_отправлен'] = ""
    df['Запрос_отправлен'] = df['Запрос_отправлен'].fillna("")
    return df


def load_teachers():
    if not os.path.exists("Преподаватели.csv"):
        pd.DataFrame(columns=["ФИО", "Телефон", "Email"]).to_csv("Преподаватели.csv", index=False)
    return pd.read_csv("Преподаватели.csv", dtype=str).fillna("")


try:
    df = load_schedule()
except FileNotFoundError:
    st.error("Файл 'Расписание_Средняя_группа_2026.csv' не найден. Убедитесь, что он в той же папке.")
    st.stop()

teachers_df = load_teachers()

# Техническая колонка для расчетов дат
df['Дата_dt'] = pd.to_datetime(df['Дата'], format='%d.%m.%Y', errors='coerce')
today = pd.to_datetime(date.today())
all_groups = sorted(df['Группа'].dropna().unique().tolist())
teacher_names_list = [name for name in teachers_df['ФИО'].tolist() if name.strip()]


# --- НАДЕЖНАЯ СИНХРОНИЗАЦИЯ ПРИВЯЗОК ---
def load_and_sync_mapping(current_groups):
    mapping_file = "Привязка_групп.csv"
    if os.path.exists(mapping_file):
        map_df = pd.read_csv(mapping_file, dtype=str).fillna("")
    else:
        map_df = pd.DataFrame(columns=["Группа", "Преподаватель"])

    existing_links = dict(zip(map_df['Группа'], map_df['Преподаватель']))

    synced_data = []
    for g in current_groups:
        teacher = existing_links.get(g, "")
        synced_data.append({"Группа": g, "Преподаватель": teacher})

    synced_df = pd.DataFrame(synced_data)
    synced_df.to_csv(mapping_file, index=False)
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
        st.info("Колонка 'Дата' имеет встроенный календарь для защиты от опечаток.")
        edit_df = df.drop(columns=['Дата_dt']).copy()
        edit_df['Дата'] = pd.to_datetime(edit_df['Дата'], format='%d.%m.%Y', errors='coerce').dt.date

        edited_df = st.data_editor(
            edit_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Дата": st.column_config.DateColumn("Дата", format="DD.MM.YYYY", required=True)
            }
        )
        if st.button("💾 Сохранить изменения таблицы", type="primary"):
            make_backup("Расписание_Средняя_группа_2026.csv")
            edited_df['Дата'] = pd.to_datetime(edited_df['Дата']).dt.strftime('%d.%m.%Y').fillna("")
            edited_df.to_csv("Расписание_Средняя_группа_2026.csv", index=False)
            st.success("Сохранено! (Резервная копия создана)")
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
                make_backup("Расписание_Средняя_группа_2026.csv")
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
                temp_df.drop(columns=['tmp_dt']).to_csv("Расписание_Средняя_группа_2026.csv", index=False)
                st.success("Добавлено! (Резервная копия создана)")
                st.rerun()

    # ВКЛАДКА 3: Сдвиг
    with tab3:
        with st.form("shift_form"):
            sh_group = st.selectbox("Группа для сдвига", all_groups)
            sh_date = st.date_input("С какой даты начинаются каникулы?", format="DD.MM.YYYY")
            sh_weeks = st.number_input("Сдвиг в неделях (каникулы = 1):", value=1, min_value=-10, max_value=10)
            if st.form_submit_button("Выполнить сдвиг"):
                make_backup("Расписание_Средняя_группа_2026.csv")
                temp_df = df.drop(columns=['Дата_dt']).copy()
                temp_df['tmp_dt'] = pd.to_datetime(temp_df['Дата'], format='%d.%m.%Y', errors='coerce')
                target_dt = pd.to_datetime(sh_date.strftime('%d.%m.%Y'), format='%d.%m.%Y')

                mask = (temp_df['Группа'] == sh_group) & (temp_df['tmp_dt'] >= target_dt)
                temp_df.loc[mask, 'tmp_dt'] += pd.Timedelta(weeks=sh_weeks)
                temp_df.loc[mask, 'Дата'] = temp_df.loc[mask, 'tmp_dt'].dt.strftime('%d.%m.%Y')

                temp_df.drop(columns=['tmp_dt']).to_csv("Расписание_Средняя_группа_2026.csv", index=False)
                st.success("Расписание сдвинуто! (Резервная копия создана)")
                st.rerun()

    # ВКЛАДКА 4: Преподаватели
    with tab4:
        colA, colB = st.columns(2)
        with colA:
            st.write("**Контакты преподавателей**")
            edited_teachers = st.data_editor(teachers_df, num_rows="dynamic", use_container_width=True,
                                             key="edit_teachers_table")
            if st.button("💾 Сохранить контакты", type="primary"):
                edited_teachers.to_csv("Преподаватели.csv", index=False)
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
                edited_mapping.to_csv("Привязка_групп.csv", index=False)
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
                    req_teacher = st.selectbox("Уточнить преподавателя:", teacher_names_list, index=default_idx)

                    if st.button("Сгенерировать текст", type="primary", use_container_width=True):
                        t_info = teachers_df[teachers_df['ФИО'] == req_teacher].iloc[0]
                        mod_dates_df = df[(df['Группа'] == req_group) & (df['Название модуля'] == req_mod)].copy()
                        mod_dates_df = mod_dates_df.sort_values(by='Дата_dt')

                        dates_str = f"с {mod_dates_df['Дата'].iloc[0]} по {mod_dates_df['Дата'].iloc[-1]}" if not mod_dates_df.empty else "даты не найдены"

                        final_message = (
                            f"Добрый день!\nПрошу открыть модуль: \"{req_mod}\"\nмоему преподавателю:\n"
                            f"{t_info['ФИО']} / {t_info['Телефон']} / {t_info['Email']}.\nДата работы по модулю: {dates_str}."
                        )
                        st.success("Готово! Копируйте:")
                        st.code(final_message, language="text")

            with col2:
                st.subheader("✅ Шаг 2: Скрыть")
                confirm_hide = st.checkbox(f"Подтверждаю скрытие модуля «{req_mod}»")

                if st.button("🚫 Скрыть из уведомлений", use_container_width=True):
                    if confirm_hide:
                        make_backup("Расписание_Средняя_группа_2026.csv")
                        mask = (df['Группа'] == req_group) & (df['Название модуля'] == req_mod) & (df['Урок'] == '1')
                        df.loc[mask, 'Запрос_отправлен'] = 'Да'
                        df.drop(columns=['Дата_dt']).to_csv("Расписание_Средняя_группа_2026.csv", index=False)
                        st.success("Модуль скрыт!")
                        st.rerun()
                    else:
                        st.error("Поставьте галочку подтверждения!")

    # ВКЛАДКА 6: Смена пароля
    with tab6:
        st.subheader("🔑 Настройка PIN-кода администратора")
        st.info(
            "Здесь вы можете изменить пароль от панели управления. Новый пароль сохранится в отдельный защищенный файл.")

        with st.form("change_pass_form"):
            new_pass1 = st.text_input("Новый PIN-код", type="password")
            new_pass2 = st.text_input("Повторите новый PIN-код", type="password")
            submit_pass = st.form_submit_button("Сохранить новый пароль")

            if submit_pass:
                if not new_pass1:
                    st.error("Пароль не может быть пустым!")
                elif new_pass1 != new_pass2:
                    st.error("Пароли не совпадают!")
                else:
                    save_admin_password(new_pass1)
                    st.success("Пароль успешно изменен! Используйте его при следующем входе.")