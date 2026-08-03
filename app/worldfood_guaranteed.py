import html
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.logger import logger
from app.models import Article
from app.telegram import TelegramPublisher
from app.worldfood import RecipeEditorialResult, WorldFoodFormatter, WorldFoodService


FALLBACK_RECIPES: tuple[RecipeEditorialResult, ...] = (
    RecipeEditorialResult(
        publish=True,
        dish_name="Мерджимек чорбасы",
        cuisine="турецкая",
        intro="Густой и согревающий суп из красной чечевицы с мягкими овощными нотами.",
        ingredients=[
            "200 г красной чечевицы",
            "1 луковица",
            "1 морковь",
            "1 небольшая картофелина",
            "1 ст. л. томатной пасты",
            "1,2 л воды или овощного бульона",
            "2 ст. л. растительного масла",
            "по 1/2 ч. л. кумина и паприки",
            "соль и лимон для подачи",
        ],
        steps=[
            "Промыть чечевицу до прозрачной воды.",
            "Мелко нарезать лук, морковь и картофель, затем слегка обжарить их в масле.",
            "Добавить томатную пасту, кумин и паприку, прогреть около минуты.",
            "Всыпать чечевицу, влить воду или бульон и варить 25–30 минут до мягкости.",
            "Пробить суп блендером до однородности, посолить и при необходимости разбавить водой.",
            "Подать горячим с долькой лимона.",
        ],
        history=(
            "Чечевичные супы давно входят в повседневную кухню Турции и соседних регионов. "
            "Мерджимек чорбасы ценят за простые продукты, сытность и мягкую пряность. "
            "Домашние варианты различаются густотой и набором специй."
        ),
        tags=["турецкая кухня", "суп", "чечевица"],
    ),
    RecipeEditorialResult(
        publish=True,
        dish_name="Лобио",
        cuisine="грузинская",
        intro="Сытное блюдо из фасоли с луком, зеленью и пряностями.",
        ingredients=[
            "400 г готовой красной фасоли",
            "1 крупная луковица",
            "2 зубчика чеснока",
            "30 г грецких орехов",
            "небольшой пучок кинзы",
            "1 ч. л. хмели-сунели",
            "1 ст. л. растительного масла",
            "соль, перец и немного винного уксуса",
        ],
        steps=[
            "Мелко нарезать лук и обжарить до мягкости.",
            "Добавить фасоль и несколько ложек воды, прогреть 8–10 минут.",
            "Часть фасоли слегка размять, чтобы блюдо стало гуще.",
            "Смешать с измельчёнными орехами, чесноком, хмели-сунели и солью.",
            "Снять с огня, добавить кинзу и немного уксуса, дать настояться 10 минут.",
        ],
        history=(
            "Лобио в Грузии называют и фасоль, и целую группу блюд из неё. "
            "Рецепты меняются от региона к региону: блюдо бывает горячим или холодным, "
            "с орехами, зеленью и разной степенью остроты."
        ),
        tags=["грузинская кухня", "фасоль", "постное"],
    ),
    RecipeEditorialResult(
        publish=True,
        dish_name="Хориатики",
        cuisine="греческая",
        intro="Свежий греческий салат с овощами, оливками и фетой.",
        ingredients=[
            "3 спелых помидора",
            "1 огурец",
            "1 зелёный сладкий перец",
            "1/2 красной луковицы",
            "120 г феты",
            "80 г оливок",
            "3 ст. л. оливкового масла",
            "1 ч. л. сушёного орегано",
            "соль по вкусу",
        ],
        steps=[
            "Крупно нарезать помидоры и огурец.",
            "Перец нарезать кольцами, лук — тонкими полукольцами.",
            "Сложить овощи в миску, добавить оливки и слегка посолить.",
            "Сверху положить цельный кусок феты или крупные ломтики.",
            "Полить оливковым маслом, посыпать орегано и подать сразу.",
        ],
        history=(
            "Название хориатики буквально означает «деревенский». "
            "Салат связывают с простой сезонной едой из свежих овощей, сыра и оливкового масла. "
            "В традиционной подаче листья салата обычно не используются."
        ),
        tags=["греческая кухня", "салат", "фета"],
    ),
    RecipeEditorialResult(
        publish=True,
        dish_name="Онигири",
        cuisine="японская",
        intro="Удобные рисовые треугольники с начинкой, которые едят как перекус или часть обеда.",
        ingredients=[
            "300 г круглозёрного риса",
            "360 мл воды",
            "1/2 ч. л. соли",
            "80 г консервированного тунца",
            "1 ст. л. майонеза",
            "2 листа нори",
        ],
        steps=[
            "Промыть рис несколько раз, залить водой и сварить под крышкой до готовности.",
            "Дать рису постоять 10 минут, затем немного остудить, не пересушивая.",
            "Смешать тунца с майонезом для начинки.",
            "Смочить руки водой, натереть солью и расплющить порцию риса на ладони.",
            "Положить начинку в центр, закрыть рисом и сформировать треугольник.",
            "Обернуть полоской нори непосредственно перед подачей.",
        ],
        history=(
            "Рисовые шарики и треугольники в Японии имеют долгую бытовую историю как удобная еда в дорогу. "
            "Начинки бывают самыми разными, от солёной рыбы до маринованных слив. "
            "Современные онигири широко продаются и в домашних вариантах, и в магазинах."
        ),
        tags=["японская кухня", "рис", "перекус"],
    ),
    RecipeEditorialResult(
        publish=True,
        dish_name="Гуакамоле",
        cuisine="мексиканская",
        intro="Кремовая закуска из авокадо с лаймом, томатом и лёгкой остротой.",
        ingredients=[
            "2 спелых авокадо",
            "1 небольшой помидор",
            "1/4 красной луковицы",
            "1/2 лайма",
            "небольшой пучок кинзы",
            "немного свежего чили",
            "соль по вкусу",
        ],
        steps=[
            "Разрезать авокадо, удалить косточки и вынуть мякоть.",
            "Размять мякоть вилкой, оставляя небольшие кусочки.",
            "Мелко нарезать помидор, лук, кинзу и чили.",
            "Смешать всё с соком лайма и солью.",
            "Подать сразу, чтобы авокадо не потемнело.",
        ],
        history=(
            "Соусы и пасты из авокадо имеют глубокие корни в кухнях Мезоамерики. "
            "Современный гуакамоле существует во множестве домашних версий. "
            "Обычно его подают свежим, поскольку вкус и цвет авокадо быстро меняются на воздухе."
        ),
        tags=["мексиканская кухня", "авокадо", "закуска"],
    ),
    RecipeEditorialResult(
        publish=True,
        dish_name="Брускетта с помидорами",
        cuisine="итальянская",
        intro="Хрустящий хлеб с чесноком, спелыми помидорами, базиликом и оливковым маслом.",
        ingredients=[
            "8 ломтиков деревенского хлеба",
            "3 спелых помидора",
            "1 зубчик чеснока",
            "небольшой пучок базилика",
            "3 ст. л. оливкового масла",
            "соль и чёрный перец",
        ],
        steps=[
            "Нарезать помидоры небольшими кубиками и слить лишний сок.",
            "Смешать их с базиликом, оливковым маслом, солью и перцем.",
            "Подсушить хлеб на сухой сковороде, гриле или в духовке.",
            "Натереть горячие ломтики разрезанным зубчиком чеснока.",
            "Выложить помидорную смесь на хлеб и сразу подать.",
        ],
        history=(
            "Брускетта относится к итальянской традиции поджаренного хлеба с простыми добавками. "
            "Её формы различаются по регионам и сезону. "
            "Вариант с помидорами стал одним из самых узнаваемых за пределами Италии."
        ),
        tags=["итальянская кухня", "закуска", "помидоры"],
    ),
    RecipeEditorialResult(
        publish=True,
        dish_name="Алу джира",
        cuisine="индийская",
        intro="Картофель с кумином и специями, простой ароматный гарнир североиндийской кухни.",
        ingredients=[
            "600 г картофеля",
            "2 ст. л. растительного масла",
            "1 ч. л. семян кумина",
            "1/2 ч. л. куркумы",
            "1/2 ч. л. молотого кориандра",
            "щепотка чили",
            "соль по вкусу",
            "кинза и лимон для подачи",
        ],
        steps=[
            "Отварить картофель почти до готовности, остудить и нарезать кубиками.",
            "Разогреть масло и прогреть семена кумина до появления аромата.",
            "Добавить куркуму, кориандр и чили, быстро перемешать.",
            "Выложить картофель и обжаривать 8–10 минут до лёгкой корочки.",
            "Посолить, добавить кинзу и немного лимонного сока.",
        ],
        history=(
            "Сочетание картофеля и кумина распространено в домашней кухне Северной Индии. "
            "Алу джира готовят как самостоятельное постное блюдо или гарнир. "
            "Набор специй и степень остроты обычно меняются по вкусу семьи."
        ),
        tags=["индийская кухня", "картофель", "гарнир"],
    ),
)


class FallbackWorldFoodFormatter(WorldFoodFormatter):
    def photo_caption(self, result: RecipeEditorialResult, article: Article) -> str:
        dish = html.escape(self._short(result.dish_name, 120))
        cuisine = html.escape(self._short(result.cuisine, 80))
        intro = html.escape(self._short(result.intro, 450))
        caption = f"<b>{dish}</b>\n\n🌍 <b>Кухня:</b> {cuisine}"
        if intro:
            caption += f"\n\n{intro}"
        caption += "\n\n<i>Редакционный резервный рецепт WorldFood</i>"
        return caption

    def history_message(self, result: RecipeEditorialResult, article: Article) -> str:
        dish = html.escape(self._short(result.dish_name, 120))
        history = html.escape(self._short(result.history, 1500))
        tags = self._tags(result.tags)
        footer = "\n\n<i>Подготовлено редакцией WorldFood</i>"
        if tags:
            footer += f"\n\n{tags}"
        return f"📜 <b>Краткая история: {dish}</b>\n\n{history}{footer}"


def select_fallback_recipe(now: datetime | None = None) -> RecipeEditorialResult:
    current = now or datetime.now(timezone.utc)
    index = int(current.strftime("%Y%m%d%H")) % len(FALLBACK_RECIPES)
    return FALLBACK_RECIPES[index]


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def create_fallback_cover(result: RecipeEditorialResult) -> Path:
    settings.image_cache_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zа-яё0-9]+", "-", result.dish_name.lower()).strip("-") or "dish"
    destination = settings.image_cache_dir / f"fallback-{slug}.jpg"

    image = Image.new("RGB", (1280, 720), (244, 235, 215))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((55, 55, 1225, 665), radius=50, fill=(255, 250, 239))
    draw.ellipse((105, 115, 585, 595), fill=(224, 216, 199), outline=(150, 135, 110), width=8)
    draw.ellipse((155, 165, 535, 545), fill=(238, 164, 83))
    draw.ellipse((220, 215, 330, 325), fill=(222, 79, 65))
    draw.ellipse((350, 260, 470, 380), fill=(77, 147, 94))
    draw.ellipse((245, 385, 380, 500), fill=(246, 205, 83))
    draw.arc((130, 140, 560, 570), 205, 335, fill=(255, 255, 255), width=12)

    title_font = _font(58, bold=True)
    cuisine_font = _font(34)
    label_font = _font(24, bold=True)
    draw.text((655, 145), "WORLD FOOD", font=label_font, fill=(120, 80, 45))

    title_lines = textwrap.wrap(result.dish_name, width=22)[:3]
    y = 220
    for line in title_lines:
        try:
            draw.text((655, y), line, font=title_font, fill=(47, 42, 36))
        except UnicodeEncodeError:
            draw.text((655, y), "WORLD FOOD RECIPE", font=title_font, fill=(47, 42, 36))
        y += 75

    cuisine = f"{result.cuisine.capitalize()} кухня"
    try:
        draw.text((655, 500), cuisine, font=cuisine_font, fill=(105, 92, 73))
    except UnicodeEncodeError:
        draw.text((655, 500), "World cuisine", font=cuisine_font, fill=(105, 92, 73))

    image.save(destination, format="JPEG", quality=91, optimize=True)
    return destination


class GuaranteedWorldFoodService(WorldFoodService):
    async def run(self) -> int:
        eligible_for_publication = self._interval_has_elapsed()
        try:
            published = await super().run()
        except RuntimeError as exc:
            if "WorldFood publication failed" in str(exc):
                raise
            logger.exception(
                "Обычная подготовка WorldFood завершилась ошибкой, включаю резерв: {}",
                exc,
            )
            published = 0

        if published or not eligible_for_publication:
            return published

        logger.warning(
            "Подходящий интернет-рецепт не найден. Публикую проверенный редакционный резерв, "
            "чтобы запуск не завершился пустым."
        )
        return await self._publish_fallback()

    async def _publish_fallback(self) -> int:
        editorial = select_fallback_recipe()
        slug = re.sub(r"[^a-zа-яё0-9]+", "-", editorial.dish_name.lower()).strip("-")
        article = Article(
            source="Редакционный резерв WorldFood",
            title=editorial.dish_name,
            url=f"fallback://worldfood/{slug}",
            content=editorial.intro,
        )
        formatter = FallbackWorldFoodFormatter()
        publisher = TelegramPublisher()
        image_path: Path | None = None

        try:
            try:
                image_path = create_fallback_cover(editorial)
                await publisher.publish_photo(
                    formatter.photo_caption(editorial, article),
                    image_path,
                )
            except Exception as exc:
                logger.warning(
                    "Резервная обложка не отправлена, публикую первый пост текстом: {}",
                    exc,
                )
                await publisher.publish_text(formatter.photo_caption(editorial, article))

            await publisher.publish_text(formatter.recipe_message(editorial))
            await publisher.publish_text(formatter.history_message(editorial, article))
        except Exception as exc:
            logger.exception("Резервная серия WorldFood не опубликована: {}", exc)
            raise RuntimeError(f"WorldFood fallback publication failed: {exc}") from exc
        finally:
            await publisher.close()

        article.image_path = image_path
        article.translated_title = editorial.dish_name
        self._database.save(
            article,
            "published",
            publication_mode=settings.run_mode,
        )
        logger.info(
            "Опубликован резервный рецепт [{}]: {} ({})",
            settings.run_mode,
            editorial.dish_name,
            editorial.cuisine,
        )
        return 1
