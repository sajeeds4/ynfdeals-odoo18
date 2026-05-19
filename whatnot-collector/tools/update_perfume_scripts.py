from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.config import POSTGRES_SIDECAR_SCHEMA
from server.postgres_cutover import _pg_connect, ensure_wave1_postgres_schema, postgres_available


SCRIPT_MAP = {
    "choco musk 6ml perfume oil": """Chat, if you love warm vanilla and chocolate scents, this is one of the safest blind buys in the whole room. Choco Musk oil is cozy, creamy, and addictive. It is not a dark bitter chocolate, it is more like soft cocoa, vanilla, and musk sitting close to the skin. This is the one you throw in your purse, keep in your car, layer under your sprays, and reach for when you want compliments without trying too hard. If you like sweet scents that feel comforting instead of loud, this is your lane.""",
    "choco musk marshmallow perfume oil": """This is Choco Musk's fluffier sister. The marshmallow here makes it feel softer, sweeter, and more airy. Think chocolate dust, vanilla, and warm skin musk with that pillowy marshmallow feel sitting on top. If regular Choco Musk is your everyday cozy scent, this one is your dessert-night version. If you like fragrances that smell edible, comforting, and super wearable, this bottle is easy money.""",
    "choco musk pistachio perfume oil": """If you already have vanilla, this is how you make the collection more interesting without leaving the comfort zone. Choco Musk Pistachio still gives you that sweet cozy dessert vibe, but the pistachio makes it nuttier, creamier, and more textured. This is for the shopper who wants sweet, but wants it to smell a little more elevated than plain sugar vanilla.""",
    "dhikra eau de parfum spray": """Dhikra starts brighter than people expect, then it turns rich. You get that sparkling bergamot and pineapple opening, and then it starts settling into florals, herbs, leather, and musk. This is not candy-sweet. This is for the buyer who wants an affordable bottle that still feels put together, warm, and polished. If you want something that smells more dressed-up than playful, Dhikra is a strong pick.""",
    "allure of oud-al-rehab": """This is a very good entry into the oud lane because it is rich without getting harsh. The opening has spice and saffron, then the woods and leather take over. It feels dry, confident, and more dressed-up than sweet. If you want something that smells expensive, structured, and mature, but still easy enough to wear, this is a smart bottle to grab.""",
    "spanish vanilla roll-on perfume oil": """Some vanilla fragrances are loud and sugary. This one is smoother than that. Spanish Vanilla is creamy, milky, soft, and comforting. It wears like a warm skin scent with sweetness instead of a sharp bakery candle vibe. If you want an easy vanilla that layers beautifully and feels soft all day, this is the move.""",
    "diala perfume in oil": """Diala is soft, creamy, and very wearable. The fruit here is not loud or sour, it melts into florals and vanilla so it feels smooth from start to finish. If you like feminine scents that feel sweet, polished, and easy to wear without being too sharp, Diala is a beautiful pick.""",
    "jourie": """Jourie is the kind of fragrance that feels pretty right away. You get a little fruit in the opening, then it turns floral and smooth, and the musk in the base keeps it soft. This is for the shopper who wants something elegant and feminine without it becoming too powdery or too sweet.""",
    "ocean breeze-al-rehab": """If you are a fresh scent person, this is easy to understand. Ocean Breeze opens bright and clean, gives you that crisp airy feel, and then the tonka and vanilla stop it from going thin. This is the kind of bottle you wear when you want to smell shower-fresh, put together, and easy to like.""",
    "million secrets al-rehab": """Million Secrets feels polished. It has that bright clean opening, then the floral heart comes in, and the vanilla-sandalwood-musk base gives it softness. If you like fragrances that feel feminine, smooth, and a little elegant instead of loud or sugary, this one makes sense.""",
    "french coffee edp spray": """French Coffee does exactly what the name promises. This smells like stepping into a cafe when the coffee is hot, the caramel is melting, and the pastry case is calling your name. It is rich, sweet, roasted, and cozy. If you want a fragrance that smells edible and makes people turn their head, this one absolutely does that.""",
    "lattafa yara - vanilla, gourmand, fruity, floral": """Yara is popular for a reason. It smells creamy, soft, feminine, and easy to wear. You get that fruity tropical sweetness in the middle, but the vanilla, musk, and sandalwood keep it smooth and fluffy instead of sticky. If someone tells me they want a pretty everyday scent that still gets attention, Yara is one of the easiest yeses in the room.""",
    "lattafa yara moi": """If the original Yara is playful, Yara Moi is the smoother, dressier version. You still get sweetness, but it is wrapped in creamy florals and a richer base. This is for the buyer who likes feminine perfumes but wants something a little more polished, a little more date-night, and a little less girly-sweet.""",
    "lattafa yara tous": """Yara Tous is the tropical one. Mango, coconut, passionfruit, and vanilla give this a sunny vacation feel right away. This is not your dark winter fragrance. This is bright, fun, easy, and happy. If somebody in chat wants something that feels like warm weather in a bottle, this is the one to show.""",
    "lattafa yara candy": """Yara Candy is for the shopper who wants sweetness with personality. The strawberry fizz effect makes it feel playful right away, and the vanilla syrup base keeps it delicious. If someone says they want cute, flirty, sweet, and fun, this is an easy recommendation.""",
    "lattafa khamrah - vanilla": """Khamrah is rich from the jump. The spice is warm, the heart is sweet, and the drydown is thick with vanilla, tonka, and amberwood. This is for the person who wants to smell cozy, expensive, and noticeable. It has that dessert-meets-amber warmth that people reach for when they want to leave a trail.""",
    "lattafa khamrah qahwa": """If Khamrah is the sweet spiced dessert, Qahwa is the version with the coffee cup next to it. You still get the warmth and richness, but the coffee note gives it texture and keeps it from feeling too sugary. This is a fantastic choice for someone who likes sweet fragrances but wants depth, roast, and a little more edge.""",
    "lattafa perfumes asad": """Asad is a confidence fragrance. It opens spicy and a little smoky, then the coffee, vanilla, and amber start pushing through and make it feel fuller and more powerful. This is the bottle I show when someone wants something bold, warm, and masculine without spending luxury-counter money.""",
    "lattafa asad zanzibar": """Zanzibar is what I show when someone says they want fresh, but not basic. You get that airy tropical feel from coconut water and salt, but the incense and vanilla underneath make it more interesting than a regular clean shower scent. It feels like vacation energy with better depth.""",
    "lattafa eclaire": """Eclaire smells like a dessert cart in perfume form. Caramel, milk, sugar, honey, vanilla, praline, this is for the shopper who wants sweet and wants it proudly. It still has enough floral softness to keep it pretty, but make no mistake, this is gourmand territory. If chat wants pastry energy, this bottle delivers.""",
    "honor & glory": """Honor and Glory stands out because that pineapple brulee opening is memorable right away. It is sweet, but not childish. Then the spices come in and the drydown turns creamy and luxe. This smells like somebody wanted a dessert fragrance but made it expensive and dressed it up.""",
    "lattafa maahir legacy": """Maahir Legacy opens bright and sharp in a very attractive way. The citrus and mint hit first, then the herbs, frankincense, and woods make it feel much more serious than a basic freshie. This is a smart buy for someone who wants fresh, masculine, and elevated.""",
    "lattafa opulent dubai": """Opulent Dubai opens with sparkle. The citrus, mango, and ginger give it lift right away, but the woods and ambergris underneath stop it from feeling simple. This is the kind of bottle that feels flashy at first spray and smoother as it settles. Great for somebody who wants energy without losing sophistication.""",
    "lattafa habik": """Habik is smooth and easy to wear. The pear in the opening gives it a fresh modern feel, then the florals soften it, and the musk-amber-oakmoss base keeps it clean and masculine. This is a very safe everyday bottle when you want something attractive that never feels too aggressive.""",
    "lattafa perfumes nebras": """Nebras is for the buyer who wants sweet, but wants it deeper than body spray sweet. The berries pull you in, then the vanilla and cacao start building, and the tonka-amber-musk base gives it warmth. This feels cozy, sexy, and easy to remember.""",
    "rasasi hawas for men": """Hawas works because it is fresh, but not thin. You get that juicy fruity-aquatic opening, and then the ambergris, musk, and woods give it staying power in the profile. This is for the guy who wants something clean and attractive that still has swagger. If you want fresh with personality, Hawas is one of the easiest crowd-pleasers out there.""",
    "rasasi hawas ice": """Hawas Ice takes the original Hawas idea and cools it down. It feels icier, more crystalline, and even more summer-ready. You still get fruit and freshness, but the frozen feel is the whole point here. If somebody wants a hot-weather attention scent, this one makes a lot of sense.""",
    "afnan supremacy collector": """Supremacy Collector's Edition gives you brightness up top, but it settles into something very polished and masculine. The pineapple and bergamot make the opening attractive immediately, and the moss, musk, and ambergris base gives it that more refined finish. This is a great bottle when someone wants something fresh enough to wear often, but upscale enough to feel special.""",
    "barakkat rouge 540": """This lives in that airy sweet amber lane that people associate with expensive niche fragrances. It has that sparkling saffron feel, a smooth musky body, and a floating trail that sits in the air. This is the kind of bottle people buy when they want something that smells expensive, clean, and instantly recognizable in a luxury style.""",
}


def main() -> None:
    if not postgres_available():
        raise SystemExit("postgres_required: update_perfume_scripts no longer writes SQLite whatnot.db")
    ensure_wave1_postgres_schema()
    conn = _pg_connect()
    cur = conn.cursor()
    updated = 0
    missing = []

    for name_fragment, script in SCRIPT_MAP.items():
        result = cur.execute(
            f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.products SET script = %s, updated_at = NOW() WHERE LOWER(name) LIKE %s",
            (script, f"%{name_fragment}%"),
        )
        if cur.rowcount:
            updated += cur.rowcount
        else:
            missing.append(name_fragment)

    conn.commit()
    conn.close()
    print(f"updated={updated}")
    if missing:
        print("missing:")
        for name in missing:
            print(f"- {name}")


if __name__ == "__main__":
    main()
