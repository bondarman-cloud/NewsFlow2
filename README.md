# Bondarman Bot Platform

Один репозиторий для нескольких независимых Telegram-ботов. Общий код отвечает за
RSS, загрузку статей, Gemini, изображения, защиту от дублей, форматирование,
публикацию в Telegram и GitHub Actions. Поведение каждого бота хранится в отдельном
профиле внутри `bots/`.

## Боты

### `hardware_news`

Новости о комплектующих, мониторах, периферии, настольных и мини-ПК. Новости о
ноутбуках исключены. Профиль использует существующую базу `data/newsflow2.db`, чтобы
не потерять историю опубликованных материалов.

### `tech_news`

Общие технологические новости из бывшего репозитория NewsFlow: AI, инструменты
разработчика, облачные платформы, безопасность, базы данных, Python, Linux и другие
значимые релизы.

## Структура

```text
app/                         общий движок
bots/
  hardware_news/
    config.yaml              параметры и поисковые запросы
    prompt.txt               редакционная политика Gemini
  tech_news/
    config.yaml
    sources.yaml
    prompt.txt
data/sources.yaml             текущие источники hardware_news
.github/workflows/
  run-bot.yml                 общий reusable workflow
  run-manual.yml              ручной запуск hardware_news
  run-scheduled.yml           автоматический hardware_news
  tech-manual.yml             ручной запуск tech_news
  tech-scheduled.yml          автоматический tech_news
```

Git-ветки используются только для разработки. Разные работающие боты являются
профилями, а не ветками репозитория.

## Запуск

```bash
python main.py --bot hardware_news --mode manual --force
python main.py --bot tech_news --mode scheduled
```

Обязательные переменные окружения:

```text
BOT_TOKEN
CHANNEL_ID
GEMINI_API_KEY
```

Дополнительно можно задать `DATABASE_PATH`, `IMAGE_CACHE_DIR`, `RUN_MODE`,
`FORCE_PUBLISH`, `MAX_ARTICLES_PER_RUN`, `MAX_CANDIDATES`, `MAX_AGE_HOURS` и
`PUBLISH_INTERVAL`.

## GitHub Secrets

Для аппаратного бота сохраняются существующие секреты:

```text
BOT_TOKEN
CHANNEL_ID
GEMINI_API_KEY
```

Для технологического бота нужно добавить в этот репозиторий:

```text
TECH_BOT_TOKEN
TECH_CHANNEL_ID
```

`GEMINI_API_KEY` используется обоими ботами. Значения секретов из другого
репозитория GitHub автоматически не переносит.

## Добавление нового новостного бота

1. Создать папку `bots/<bot_id>/`.
2. Добавить `config.yaml`, `sources.yaml` и `prompt.txt`.
3. Выбрать существующий фильтр `hardware` или `tech`, либо добавить новый класс в
   `app/filtering.py` и зарегистрировать его в `build_filter()`.
4. Создать маленький workflow, вызывающий `.github/workflows/run-bot.yml`.
5. Выдать боту отдельные Telegram-секреты, базу данных и cache prefix.

Пример профиля:

```yaml
id: example_news
title: Example News
filter: tech
base_tag: новости
sources: bots/example_news/sources.yaml
prompt: bots/example_news/prompt.txt
require_image: false

defaults:
  max_articles_per_run: 1
  max_candidates: 500
  max_age_hours: 336
  publish_interval: 3300

discovery_queries: []
```

## Боты с другим функционалом

Текущий общий pipeline рассчитан на публикацию новостей. Следующий тип приложения,
например монитор цен, вакансий или GitHub-релизов, добавляется отдельным service-классом
и регистрируется в runner. Telegram, конфигурация, логирование, Gemini и хранилище при
этом остаются общими. Не нужно копировать весь репозиторий ради каждого нового бота.

## Проверки

CI компилирует проект, запускает Ruff, Pytest и проверяет оба профиля. Изменения
сначала разрабатываются в отдельной ветке и только после зелёного CI объединяются с
`main`.
