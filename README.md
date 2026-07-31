# Bondarman Bot Platform

Один репозиторий для нескольких независимых Telegram-ботов. Общий код отвечает за
RSS, загрузку страниц, Gemini, изображения, защиту от дублей, Telegram и GitHub
Actions. Поведение каждого бота хранится в отдельном профиле внутри `bots/`.

## Боты

### `hardware_news`

Новости о комплектующих, мониторах, периферии, настольных и мини-ПК. Новости о
ноутбуках исключены. Профиль использует базу `data/newsflow2.db`, чтобы сохранять
историю опубликованных материалов.

### `tech_news`

Общие технологические новости: AI, инструменты разработчика, облачные платформы,
безопасность, базы данных, Python, Linux и значимые релизы.

### `worldfood_bot`

Бот мировой кухни. Он берёт материалы из настраиваемых RSS-источников, загружает
страницу рецепта и фотографию, а затем проверяет и структурирует материал через
Gemini. Одно блюдо публикуется серией из трёх сообщений:

1. фотография готового блюда, название и конкретная кухня;
2. ингредиенты и пошаговый рецепт;
3. краткая история блюда и ссылка на источник.

Подборки, рекламные страницы, ресторанные обзоры и материалы без полноценного
рецепта отклоняются. Источники и редакционные правила находятся в
`bots/worldfood_bot/`.

## Структура

```text
app/                         общий движок и сервисы
  service.py                 новостной pipeline
  worldfood.py               pipeline рецептов и серии из трёх постов
bots/
  hardware_news/
  tech_news/
  worldfood_bot/
    config.yaml
    sources.yaml
    prompt.txt
data/sources.yaml             источники hardware_news
.github/workflows/
  run-bot.yml                 общий reusable workflow
  run-manual.yml              ручной запуск hardware_news
  tech-manual.yml             ручной запуск tech_news
  worldfood-manual.yml        ручной запуск worldfood_bot
  hourly-publish.yml          внешний почасовой триггер новостных ботов
```

Git-ветки используются только для разработки. Работающие боты являются профилями,
а не отдельными ветками репозитория.

## Локальный запуск

```bash
python main.py --bot hardware_news --mode manual --force
python main.py --bot tech_news --mode manual --force
python main.py --bot worldfood_bot --mode manual --force
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

Для аппаратного бота:

```text
BOT_TOKEN
CHANNEL_ID
GEMINI_API_KEY
```

Для технологического бота:

```text
TECH_BOT_TOKEN
TECH_CHANNEL_ID
```

Для WorldFood:

```text
WORLDFOOD_BOT_TOKEN
WORLDFOOD_CHANNEL_ID
```

`GEMINI_API_KEY` используется всеми ботами. Значения секретов между репозиториями
GitHub автоматически не переносит.

После добавления WorldFood-секретов ручной тест запускается через:

```text
Actions → Run WorldFood manually → Run workflow
```

Автоматический запуск WorldFood намеренно не включён, пока не проверены качество
источников, формат трёх сообщений и отдельный Telegram-канал.

## Добавление нового бота

1. Создать папку `bots/<bot_id>/`.
2. Добавить `config.yaml`, `sources.yaml` и `prompt.txt`.
3. Указать `application: news` для новостного pipeline либо зарегистрировать новый
   service-класс в `main.py`.
4. Выбрать существующий фильтр или добавить новый в `app/filtering.py`.
5. Создать маленький workflow, вызывающий `.github/workflows/run-bot.yml`.
6. Выдать боту отдельные Telegram-секреты, базу данных и cache prefix.

## Проверки

CI компилирует проект, запускает Ruff, Pytest и проверяет профили `hardware_news`,
`tech_news` и `worldfood_bot`. Изменения сначала разрабатываются в отдельной ветке и
объединяются с `main` только после успешных проверок.
