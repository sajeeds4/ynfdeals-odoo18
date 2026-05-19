#!/usr/bin/env python3
"""
Generate live stream reading scripts for all products and save to DB.
Scripts are interactive, fun, and designed to engage viewers during Whatnot live auctions.
Includes audience interaction prompts, questions, and hype energy.
"""

LEGACY_SQLITE_RETIRED = (
    "generate_scripts.py is retired because it writes directly to SQLite. "
    "Use a Postgres-backed product script backfill path instead."
)

# Interactive, engaging scripts keyed by product ID
# Style: conversational, audience interaction, questions, hype, fun facts
SCRIPTS = {
    # ── Afnan ──────────────────────────────────────────────────────
    128: (
        "Alright chat, who's ready for a BANGER?!\n"
        "This is 9 PM Night Out by Afnan — Extrait de Parfum, 3.4 oz, unisex.\n"
        "Extrait means this is the STRONGEST concentration — longer lasting, more depth.\n"
        "Think about your best night out — that's this scent. Warm, spicy, seductive.\n\n"
        "Who's going out this weekend? Drop a comment if you need a new going-out scent!\n\n"
        "Afnan is one of the top perfume houses from the UAE — they don't miss.\n"
        "Retail is around $49, we're starting LOW. Who wants it?!"
    ),
    38: (
        "OK OK OK — Afnan Supremacy Collector's Edition!\n"
        "Who here has tried Afnan before? Let me know in the chat!\n\n"
        "This opens with pineapple and bergamot — fresh and fruity.\n"
        "Then boom — orange blossom and birch hit you in the middle.\n"
        "Base is oakmoss, musk, and ambergris — LUXURY.\n\n"
        "Fun fact: this lasts 10 to 12 HOURS. You put this on in the morning,\n"
        "people are STILL smelling you at dinner.\n\n"
        "3.4 oz EDP, retails around $59. Who's adding this to their collection?!"
    ),

    # ── Fragrance World / Maison Alhambra ────────────────────────
    90: (
        "Ace of Spades by Fragrance World! Who knows what this is a dupe of?\n"
        "Drop it in the chat if you know!\n\n"
        "That's right — Creed Aventus! The $400+ king of niche fragrances.\n"
        "Smoky pineapple, birch, patchouli, vanilla, and musk.\n"
        "You're getting that Aventus DNA at a FRACTION of the price.\n\n"
        "If you've been wanting to try the Aventus vibe, THIS is your chance.\n"
        "100ml bottle, starting low — who's bidding?!"
    ),
    78: (
        "Oud lovers, where you AT?! Make some noise in the chat!\n\n"
        "Al Oud Al Baree by Fragrance World — 100ml EDP.\n"
        "This is a clean, elegant oud — not harsh, not smoky, just PERFECT.\n"
        "It's that Arabian luxury that turns heads wherever you go.\n\n"
        "Have you ever gotten a compliment from a stranger? That's what oud does.\n"
        "100ml bottle, amazing longevity. Who needs this?!"
    ),
    103: (
        "Amber D'Or — Golden Amber! Who loves warm, cozy scents?\n"
        "If that's you, put a YES in the chat!\n\n"
        "This is like wrapping yourself in a warm golden blanket.\n"
        "Sweet, resinous, warm amber — perfect for fall, winter, date nights.\n"
        "100ml EDP by Fragrance World.\n\n"
        "If you've never tried an amber fragrance, START HERE.\n"
        "Starting low, who wants it?!"
    ),
    109: (
        "Avant by Fragrance World — clean, fresh, modern.\n"
        "Who here prefers fresh scents over heavy ones? Raise your hand in chat!\n\n"
        "This is your everyday go-to — office-friendly, versatile, just CLEAN.\n"
        "The kind of scent where people lean in and say 'you smell nice.'\n\n"
        "Starting it low!"
    ),
    102: (
        "Avant INTENSE — the bigger, bolder brother!\n"
        "If you liked Avant, you'll LOVE this one.\n\n"
        "More depth, more projection, more compliments.\n"
        "Same DNA but turned up to 11.\n"
        "Who wants to upgrade? 100ml bottle, starting low!"
    ),
    86: (
        "LADIES! Belle Dolce Red Delice is here!\n"
        "Who loves fruity, flirty, feminine scents? Let me see those comments!\n\n"
        "Sweet red fruits, floral heart, and a warm sexy base.\n"
        "Think brunch with the girls, date night, or just feeling YOURSELF.\n\n"
        "100ml EDP, full size. Starting low — ladies, don't sleep on this!"
    ),
    92: (
        "Berries Weekend Violet! Who's excited for the weekend?!\n"
        "Drop what you're doing this weekend in the chat!\n\n"
        "Berry and violet blend — fruity, floral, fresh.\n"
        "This IS your weekend scent. Fun, easy, everyone likes it.\n"
        "100ml bottle, spring and summer vibes. Starting low!"
    ),
    91: (
        "CHOCOLATE LOVERS, where are you?! Drop a chocolate emoji if that's you!\n\n"
        "C.A.C.A.O. by Fragrance World — 100ml EDP.\n"
        "Rich, warm, gourmand CHOCOLATE fragrance.\n"
        "Cocoa, vanilla, warm spices — you literally smell like dessert.\n\n"
        "I dare someone to wear this and NOT get a compliment.\n"
        "Fall and winter MUST-HAVE. Starting low!"
    ),
    93: (
        "Celestia Blu — who loves blue fragrances?!\n"
        "If Bleu de Chanel or Versace Dylan Blue is your thing, listen up!\n\n"
        "Fresh, aquatic, ocean vibes. Clean and crisp.\n"
        "Perfect for summer, the office, or just everyday freshness.\n"
        "100ml bottle, starting low!"
    ),
    107: (
        "Celestia Hazel — OK this one is UNIQUE.\n"
        "Hazelnut meets warm amber and soft woods.\n"
        "Anyone here love nutty scents? Let me know!\n\n"
        "Cozy, comforting, a real conversation starter.\n"
        "People will ask 'what ARE you wearing?'\n"
        "100ml full size, starting low!"
    ),
    98: (
        "Divin Aoud — DIVINE OUD. It's in the name!\n"
        "Oud fans, this is your moment — type OUD in the chat!\n\n"
        "Rich, luxurious oud with rose and warm resins.\n"
        "Arabian luxury at its finest.\n"
        "Long lasting, great projection, commands attention.\n"
        "100ml bottle — who's adding this to the collection?!"
    ),
    80: (
        "Enigma Deux — chapter TWO of the Enigma series.\n"
        "Who loves mystery? Who loves not knowing what someone's wearing?\n\n"
        "Mysterious, sophisticated, layered — keeps people guessing.\n"
        "Warm woody base with aromatic spices.\n"
        "100ml, starting low!"
    ),
    88: (
        "Enigma Quatre — chapter FOUR!\n"
        "Anyone collecting the Enigma series? Let me know!\n\n"
        "Each one has its own personality — this one is bold and complex.\n"
        "Spicy, woody, with a touch of sweetness.\n"
        "100ml, starting low!"
    ),
    82: (
        "Enigma Une — the one that STARTED it all!\n"
        "Chapter one. The original mystery.\n\n"
        "Mysterious, captivating, unforgettable.\n"
        "Woody, spicy, smooth amber finish.\n"
        "A true signature scent. Who wants the original? Starting low!"
    ),
    87: (
        "Essence de Noir — Essence of DARKNESS.\n"
        "Who here is a night owl? Dark scent lovers, this is YOUR time!\n\n"
        "Dark oud, smoky incense, vanilla base.\n"
        "This is your evening POWER scent.\n"
        "Heads WILL turn. 100ml, starting low!"
    ),
    110: (
        "Expose Pour Elle — for HER!\n"
        "Ladies, are you still here? Make some noise!\n\n"
        "Floral, elegant, feminine, warm.\n"
        "Great for everyday or special occasions.\n"
        "Starting low!"
    ),
    76: (
        "Expose Pour Lui — for HIM!\n"
        "Gentlemen, your turn! Who needs a new daily scent?\n\n"
        "Fresh, masculine, confident — the kind that gets noticed.\n"
        "Woody, aromatic, clean — perfect daily driver.\n"
        "100ml, starting low!"
    ),
    99: (
        "Expose Unisexe — ANYONE can wear this!\n"
        "Who here shares fragrances with their partner? Drop a YES!\n\n"
        "Balanced fresh, floral, and woody notes.\n"
        "Super versatile, any season, any occasion.\n"
        "80ml bottle, starting low!"
    ),
    115: (
        "Atom Grey — sleek, modern, sophisticated.\n"
        "Who loves that clean suit-and-tie energy? This is it.\n\n"
        "Fresh and clean with a smoky edge.\n"
        "Office-friendly but still makes a STATEMENT.\n"
        "100ml, starting low!"
    ),
    70: (
        "Y'ALL KNOW WHAT THIS IS!\n"
        "Barakkat Rouge 540 — the FAMOUS Baccarat Rouge dupe!\n"
        "Who's tried the original? Drop a comment!\n\n"
        "Saffron, jasmine, amberwood, fir resin — THAT iconic scent.\n"
        "This is the EXTRAIT version — even stronger and longer lasting.\n\n"
        "People pay $300+ for the Maison Francis Kurkdjian original.\n"
        "You're getting this for a FRACTION.\n"
        "One of the BEST dupes on the market, period. Starting LOW!"
    ),
    125: (
        "The Promise — a promise of LUXURY.\n"
        "Who here believes in keeping promises? This one delivers!\n\n"
        "Sweet, spicy, creamy vanilla. Unisex.\n"
        "Warm and inviting — the kind of scent that hugs you.\n"
        "Starting low, who wants it?!"
    ),
    101: (
        "Glacier Bold — who needs to COOL DOWN?!\n"
        "Fresh, icy, cool — like standing next to a mountain glacier.\n\n"
        "If you love fresh blue fragrances, drop ICE in the chat!\n"
        "Perfect for hot summer days, the gym, everyday freshness.\n"
        "100ml, super refreshing. Starting low!"
    ),
    96: (
        "Glorious Oud — GLORIOUS is the word!\n"
        "Premium oud, rich amber, touch of rose.\n"
        "Oud fans, I'm looking at you — type GLORY in the chat!\n\n"
        "Arabian luxury that speaks for ITSELF.\n"
        "80ml, incredible quality. Starting low!"
    ),
    85: (
        "Happiness Oud — oud that makes you HAPPY!\n"
        "Who said oud has to be dark and heavy? NOT THIS ONE.\n\n"
        "Lighter, sweeter take on traditional oud.\n"
        "Warm, comforting, uplifting — puts a smile on your face.\n"
        "80ml, starting low!"
    ),
    116: (
        "INTENSE GOLD Pour Femme — ladies, this is GOLD!\n"
        "Who wants to feel like a golden goddess? Comment below!\n\n"
        "Rich, warm, golden amber with beautiful florals.\n"
        "Luxurious, elegant, perfect for special occasions.\n"
        "3.4 oz full size, starting low!"
    ),
    97: (
        "Intense Silver Pour Homme — the MASCULINE counterpart!\n"
        "Silver vs Gold — which team are you? Drop SILVER or GOLD!\n\n"
        "Cool, metallic, fresh with woody depth.\n"
        "Modern, clean, sophisticated.\n"
        "100ml, starting low!"
    ),
    104: (
        "King of Diamonds — feel like ROYALTY!\n"
        "Who's the king in here tonight?!\n\n"
        "Bright, sparkling top notes with a rich woody base.\n"
        "Luxurious but wearable. 80ml, starting low — claim your crown!"
    ),
    74: (
        "Queen of Hearts — the QUEEN has arrived!\n"
        "Ladies, type QUEEN if that's you!\n\n"
        "Sweet, fruity, floral — irresistibly feminine.\n"
        "A scent that captures hearts wherever you go.\n"
        "80ml, starting low — claim YOUR crown!"
    ),
    108: (
        "S.A.L.T. — a SALTY aquatic scent!\n"
        "Beach lovers, ocean lovers, who's here?!\n\n"
        "Think ocean breeze with a twist — fresh, clean, addictive.\n"
        "Perfect for summer and anyone who loves the sea.\n"
        "100ml, starting low!"
    ),
    77: (
        "Suspenso Intense — SUSPENSE and INTENSITY!\n"
        "Who loves a good mystery? This IS the thriller of fragrances.\n\n"
        "Dark, mysterious, smoky — keeps people guessing.\n"
        "Keeps them coming CLOSER.\n"
        "100ml, starting low!"
    ),
    112: (
        "Taraf — that's LUXURY in Arabic!\n"
        "Who here appreciates the finer things? Type LUXURY!\n\n"
        "Rich, opulent, warm — Arabian luxury experience.\n"
        "Warm spices, oud, amber — the WHOLE package.\n"
        "Starting low!"
    ),
    89: (
        "The Shadow — EXTRAIT de Parfum!\n"
        "Extrait means it's the STRONGEST concentration. This lasts ALL DAY.\n"
        "Dark, mysterious, long-lasting shadow.\n\n"
        "Who wants to leave a trail that people remember?\n"
        "70ml, extrait quality. Starting low!"
    ),
    105: (
        "TOBACCO D'FEU — Tobacco and FIRE!\n"
        "Smokers, non-smokers, everyone loves a good tobacco scent.\n"
        "Who agrees? Drop a FIRE emoji!\n\n"
        "Rich tobacco leaf, warm spices, vanilla, amber.\n"
        "Your fireside fragrance — cozy, bold, irresistible.\n"
        "Fall and winter essential. 100ml, starting low!"
    ),
    83: (
        "Volute Intense — spiraling layers of complexity!\n"
        "Who here loves a scent that CHANGES throughout the day?\n\n"
        "Warm, spicy, woody with a resinous base.\n"
        "You'll smell something new every hour.\n"
        "100ml, starting low!"
    ),
    75: (
        "Y.U.Z.U. — Japanese YUZU citrus freshness!\n"
        "Citrus gang, where are you?! Drop FRESH in the chat!\n\n"
        "Bright, zesty, energizing yuzu with clean woody notes.\n"
        "Perfect for spring and summer — super refreshing.\n"
        "If you love citrus, this is a MUST.\n"
        "100ml, starting low!"
    ),
    79: (
        "Pur Classique — PURE classic elegance!\n"
        "Who loves a timeless, refined scent? The kind that never goes out of style?\n\n"
        "Clean, balanced, works for ANY occasion.\n"
        "Your signature scent starter. 100ml, starting low!"
    ),
    95: (
        "Pur Intoxique — INTOXICATING and pure!\n"
        "Once you smell this, you're HOOKED. Fair warning!\n\n"
        "Dark, sweet, mysterious — addictive vibes.\n"
        "Great for evenings and special occasions.\n"
        "100ml, starting low!"
    ),
    81: (
        "Vie Brise — the BREEZE of life!\n"
        "Who here just wants something light and easy to wear?\n\n"
        "Airy, fresh, subtle florals — effortless everyday scent.\n"
        "80ml, starting low!"
    ),
    84: (
        "Vie Ciel — the SKY of life!\n"
        "Bright, uplifting, like a perfect clear sky day.\n"
        "Who needs some good vibes? This scent IS good vibes!\n\n"
        "Fresh, clean, beautiful. 80ml, starting low!"
    ),
    106: (
        "Vie Eau — the WATER of life!\n"
        "Aquatic, fresh, clean — refreshing like cool water.\n"
        "Who's thirsty for a good scent? Drop WATER!\n\n"
        "Everyday versatility at its finest.\n"
        "80ml, starting low!"
    ),
    123: (
        "Vie Sol — the SUN of life!\n"
        "Warm, radiant, sunny vibes in a bottle!\n"
        "Who's ready for summer? Drop a SUN emoji!\n\n"
        "Bright citrus meets warm amber — sunshine energy.\n"
        "Unisex, 2.7 oz, starting low!"
    ),
    129: (
        "Dynasty — POWERFUL, REGAL, COMMANDING.\n"
        "Who wants to build a legacy? This is the fragrance for it!\n\n"
        "Rich, warm, oriental — the kind that turns heads and opens doors.\n"
        "Unisex, 3.4 oz. Starting low!"
    ),
    127: (
        "Optimystic White — stay OPTIMISTIC!\n"
        "Who here is feeling positive tonight? GOOD VIBES ONLY!\n\n"
        "Clean, bright, uplifting — white florals, soft musk, clean woods.\n"
        "A feel-good fragrance for everyday.\n"
        "3.4 oz unisex, starting low!"
    ),
    100: (
        "Perfume For Generation 01 — the NEW WAVE!\n"
        "New to fragrances? This is your perfect starting point.\n"
        "Already a collector? This adds something FRESH.\n\n"
        "Modern, versatile, crowd-pleasing.\n"
        "90ml, starting low!"
    ),
    124: (
        "Generation 02 — the SEQUEL that's even BETTER!\n"
        "Who tried Gen 01? How was it? Let me know!\n\n"
        "Evolved, refined, more complex layers.\n"
        "3.0 oz unisex, starting low!"
    ),
    120: (
        "Posh Alpha — ALPHA ENERGY!\n"
        "Who's the alpha in the chat tonight? Show yourself!\n\n"
        "Bold woody and spicy notes that command RESPECT.\n"
        "Unisex, 2.7 oz. Starting low!"
    ),
    119: (
        "Posh Mirage — like a desert MIRAGE!\n"
        "Exotic, alluring, shimmering — you see it, you want it.\n"
        "Who loves exotic scents? Drop MIRAGE!\n\n"
        "Sweet, warm, mysterious.\n"
        "Unisex, 2.7 oz, starting low!"
    ),
    94: (
        "Posh Omega — the FINAL CHAPTER!\n"
        "Omega means THE END — this is the ultimate.\n"
        "Who wants the end-game fragrance?!\n\n"
        "Rich, deep, complex — warm woody luxury.\n"
        "80ml, starting low!"
    ),

    # ── Amwaaj ─────────────────────────────────────────────────────
    114: (
        "Bait Al Oud by Amwaaj — the HOUSE of OUD!\n"
        "Who speaks Arabic? Bait Al Oud = House of Oud.\n\n"
        "Rich, traditional Arabian oud with warm spices.\n"
        "If you appreciate REAL oud, this is a must-have.\n"
        "3.4 oz unisex. Starting low!"
    ),
    121: (
        "Kunooz by Amwaaj — TREASURES in Arabic!\n"
        "Who wants to find a hidden treasure tonight?!\n\n"
        "Rich, warm, layered oriental.\n"
        "Warm spices, amber, a hint of sweetness.\n"
        "3.4 oz unisex, starting low!"
    ),
    113: (
        "Malaaki by Amwaaj — that means MY ANGEL!\n"
        "Tag someone who's your angel in the chat!\n\n"
        "Soft, heavenly, beautiful — delicate oriental.\n"
        "Elegant, refined, subtle luxury.\n"
        "2.8 oz unisex, starting low!"
    ),

    # ── Armaf ──────────────────────────────────────────────────────
    117: (
        "Skin Couture Sport by ARMAF!\n"
        "Who here is into fitness? Gym rats, speak up!\n\n"
        "Sporty, fresh, clean — your post-workout flex.\n"
        "Light, energizing, great projection.\n"
        "3.4 oz EDT, starting low!"
    ),
    122: (
        "Armaf Oros Oud — with SWAROVSKI CRYSTALS on the bottle!\n"
        "Yes, you heard that right — real Swarovski crystals!\n"
        "Who's buying this as a GIFT? Perfect present right here!\n\n"
        "Rich oud fragrance in a STUNNING bottle.\n"
        "1.7 oz EDP. Starting low!"
    ),

    # ── Al Haramain ────────────────────────────────────────────────
    126: (
        "L'aventure Knight by Al Haramain!\n"
        "Al Haramain is LEGENDARY — they've been making fragrances for decades.\n"
        "Who knows Al Haramain? Drop a comment!\n\n"
        "Bold, adventurous, masculine — woody, spicy, aromatic.\n"
        "The knight's armor in scent form.\n"
        "100ml EDP. Starting low!"
    ),

    # ── Lattafa ────────────────────────────────────────────────────
    35: (
        "THE ORIGINAL YARA! The one that went VIRAL on TikTok!\n"
        "Who's seen this on social media? Drop a YES!\n\n"
        "Vanilla, gourmand, fruity, floral — EVERYTHING you love.\n"
        "This is the most talked-about fragrance out there right now.\n"
        "Sweet, feminine, absolutely ADDICTIVE.\n"
        "If you haven't tried Yara yet, NOW is your chance. Starting LOW!"
    ),
    39: (
        "Lattafa Angham — who loves lavender? Type LAVENDER!\n\n"
        "Opens with bright citrus and fresh lavender.\n"
        "Heart of warm amber and soft musk.\n"
        "Dries down to a creamy vanilla that just HUGS you.\n\n"
        "Day or evening, this works for everything.\n"
        "Retails around $50, starting LOW!"
    ),
    54: (
        "Angham Second Song — the SEQUEL!\n"
        "Anyone try the original Angham? How was it? Tell me!\n\n"
        "Bergamot and pear up top, orange blossom and praline in the heart.\n"
        "Vanilla and tonka bean base — absolutely BEAUTIFUL.\n"
        "Strong longevity, perfect for cooler weather. Starting low!"
    ),
    48: (
        "Lattafa Asad BOURBON!\n"
        "Who here likes bourbon? Or whiskey? Or just warm cozy scents?\n"
        "Drop your drink of choice in the chat!\n\n"
        "This smells like bourbon whiskey in a BOTTLE.\n"
        "Rum, vanilla, tonka bean, woody amber — WARM and BOOZY.\n"
        "8 to 10 hours of longevity — BEAST MODE.\n\n"
        "Perfect for fall and winter. Retails $45, starting LOW!"
    ),
    57: (
        "Lattafa Asad ELIXIR — the CONCENTRATED version!\n"
        "If Asad is a 10, this is a 15. Cranked up EVERYTHING.\n\n"
        "Pink pepper, saffron, tobacco, cedarwood.\n"
        "Patchouli and dry amber base — absolute FIRE.\n\n"
        "Who wants something POWERFUL? This is it.\n"
        "Retails $50, starting low!"
    ),
    65: (
        "Asad ZANZIBAR — tropical vibes!\n"
        "Who's dreaming of a vacation? Where would you go? Tell me!\n\n"
        "Coconut, spice, vanilla — tropical PARADISE.\n"
        "Lavender opening, vanilla and incense base.\n"
        "THE summer fragrance.\n"
        "Retails $45, starting low!"
    ),
    62: (
        "Bade'e Al Oud Honor & Glory!\n"
        "Listen to this opening — PINEAPPLE and CREME BRULEE!\n"
        "Who thought perfume could smell like dessert AND royalty? Drop GLORY!\n\n"
        "Cinnamon, black pepper, benzoin in the heart.\n"
        "Vanilla, sandalwood, cashmeran base — absolutely REGAL.\n"
        "Exceptional longevity. Retails $45, starting LOW!"
    ),
    42: (
        "Lattafa ECLAIRE!\n"
        "Ladies, do you like pastries? Caramel? Vanilla?\n"
        "Drop your favorite dessert in the chat!\n\n"
        "This opens with caramel, milk, and sugar — like a French PASTRY!\n"
        "Honey and white flowers heart.\n"
        "Vanilla, praline, musk base — pure DESSERT.\n\n"
        "If you love sweet scents, THIS IS THE ONE.\n"
        "Retails $45, starting low!"
    ),
    55: (
        "Lattafa Fakhar for Women!\n"
        "Pomegranate, lily, peach — fresh and FRUITY.\n"
        "Who loves fruity florals? This is GORGEOUS.\n\n"
        "Tuberose, jasmine, rose, gardenia heart — like walking through a garden.\n"
        "Vanilla, white musk, sandalwood base.\n"
        "Retails around $31, starting low!"
    ),
    49: (
        "Lattafa Fakhar for MEN!\n"
        "Guys, who needs a solid everyday scent? This is IT.\n\n"
        "Apple, bergamot, ginger — fresh and energizing.\n"
        "Lavender, sage, juniper berries heart.\n"
        "Tonka, cedar, amberwood base. 6 to 8 hours easy.\n\n"
        "Clean, modern, office-friendly. Retails $45, starting low!"
    ),
    44: (
        "Lattafa Habik!\n"
        "Fun fact: Habik can mean 'your love' in Arabic. Who's feeling romantic?\n\n"
        "Bergamot and pear opening — super fresh.\n"
        "Jasmine and lily of the valley heart.\n"
        "Musk, amber, oakmoss base.\n"
        "Retails $45, starting low!"
    ),
    59: (
        "Her Confession — ladies, what's YOUR confession?\n"
        "Drop something fun in the chat, I want to hear it!\n\n"
        "Cinnamon and mysterious opening — intimate and sensual.\n"
        "Tuberose, jasmine, incense heart.\n"
        "Vanilla, tonka, musk base — whispered secrets.\n"
        "Perfect date night scent. Retails $50, starting low!"
    ),
    66: (
        "HIS Confession — gentlemen, your turn!\n"
        "What's your fragrance confession? How many do you own? Tell me!\n\n"
        "Cinnamon, lavender, mandarin — confident and bold.\n"
        "Iris, benzoin, cypress heart.\n"
        "Vanilla, tonka, amber, cedarwood, incense, patchouli — LOADED.\n"
        "Date night WINNER. Retails $50, starting low!"
    ),
    36: (
        "KHAMRAH TIME! Who already has this? Who NEEDS this?!\n"
        "This is one of the MOST HYPED Lattafa fragrances EVER!\n\n"
        "Cinnamon, nutmeg, bergamot — warm and spicy.\n"
        "Dates, praline, tuberose — the heart is INSANE.\n"
        "Vanilla, tonka, amberwood, myrrh — STRONG and LONG LASTING.\n\n"
        "Fans compare it to JPG Le Male. If you know, you know!\n"
        "Retails $50 — we're starting WAY LOW!"
    ),
    37: (
        "Khamrah QAHWA — that means COFFEE!\n"
        "COFFEE LOVERS, this is YOUR moment! Drop COFFEE in the chat!\n\n"
        "Cinnamon, cardamom, ginger opening.\n"
        "Praline, caramel, and REAL COFFEE in the heart.\n"
        "Vanilla, tonka, benzoin, musk base.\n\n"
        "If you love the smell of fresh coffee, this is HEAVEN.\n"
        "Retails $50, starting low!"
    ),
    60: (
        "Maahir Legacy!\n"
        "This opening is LOADED — lime, mint, grapefruit, lavender, AND pineapple!\n"
        "Who loves complex fragrances? Drop LEGACY!\n\n"
        "Black pepper, juniper, rosemary, frankincense heart.\n"
        "Ambroxan, vetiver, oakmoss, tonka base.\n"
        "8 to 10 HOURS. Fresh AND deep — best of both worlds.\n"
        "Retails $45, starting low!"
    ),
    56: (
        "Delilah Pour Femme by Maison Alhambra!\n"
        "Inspired by Dolce & Gabbana — who's tried the original?\n\n"
        "Rhubarb, litchi, bergamot opening — so FRESH.\n"
        "Turkish rose, peony, lily heart.\n"
        "White musk, cashmeran, vanilla base.\n"
        "Light, powdery, perfect for spring. Retails $40, starting low!"
    ),
    46: (
        "Opulent DUBAI!\n"
        "Who wants to smell like DUBAI LUXURY?!\n"
        "Drop DUBAI in the chat if you've ever wanted to go!\n\n"
        "Lemon, ginger, grapefruit, mango — sparkling opening.\n"
        "Jasmine, violet, cedarwood heart.\n"
        "Ambergris, oakmoss, benzoin, sandalwood base.\n"
        "Retails $40, starting low!"
    ),
    40: (
        "Lattafa ASAD — the LION!\n"
        "Asad means LION in Arabic — who's the lion here tonight?!\n"
        "Type LION if you're ready!\n\n"
        "Powerful, warm, woody with amber and musk.\n"
        "One of Lattafa's FLAGSHIP scents — massive following.\n"
        "100ml, excellent longevity. Starting low!"
    ),
    41: (
        "Yara Candy — the SWEET version!\n"
        "Who has a sweet tooth? Drop CANDY!\n\n"
        "Vanilla, fruits, citrus, florals — like candy for your skin.\n"
        "If you love sweet scents, this is calling YOUR name.\n"
        "Starting low!"
    ),
    43: (
        "Yara Candy EDP — the FULL SIZE!\n"
        "The EDP version — longer lasting sweetness!\n"
        "Yara fans, you NEED this in the collection.\n\n"
        "Vanilla, citrus, floral — candy sweetness that LASTS.\n"
        "Starting low!"
    ),
    45: (
        "OUD FOR GLORY! One of Lattafa's BIGGEST hits!\n"
        "If you've been wanting to try a premium oud, START HERE.\n"
        "Who loves oud? Drop OUD in the chat!\n\n"
        "Rich oud, warm amber, sweet vanillic base.\n"
        "Smells like a MILLION BUCKS.\n"
        "Incredible longevity and projection. Starting low!"
    ),
    47: (
        "Lattafa Rave Now!\n"
        "Who's ready to PARTY?! Drop your favorite party song!\n\n"
        "Sweet, fruity, warm vanilla base.\n"
        "Fun, energetic, bold — the party fragrance.\n"
        "100ml, starting low!"
    ),
    50: (
        "Lattafa Pride Vintage Radio!\n"
        "Who here loves vintage things? Old school vibes?!\n\n"
        "Warm, nostalgic, classic — like an old radio playing your favorite jam.\n"
        "Rich, warm, woody. 100ml unisex.\n"
        "Starting low!"
    ),
    51: (
        "Qaed Al Fursan — LEADER of the KNIGHTS!\n"
        "Who's ready to lead?! Drop KNIGHT in the chat!\n\n"
        "Bold, powerful, commanding.\n"
        "Woody, spicy, confident amber base.\n"
        "Starting low!"
    ),
    52: (
        "Yara Tous — the TROPICAL Yara!\n"
        "Yara fans, how many Yaras do you own? Tell me!\n\n"
        "Tropical, fruity, floral, vanilla — warm weather PERFECTION.\n"
        "Sweet, fun, super wearable.\n"
        "100ml, starting low!"
    ),
    53: (
        "Art of Universe — COSMIC VIBES!\n"
        "Who here loves something DIFFERENT? Something unique?\n\n"
        "This is hard to pin down — in the BEST way.\n"
        "Intriguing, different, conversation-starting.\n"
        "100ml unisex, starting low!"
    ),
    58: (
        "Jean Lowe IMMORTAL by Maison Alhambra!\n"
        "IMMORTAL — because this scent lives FOREVER.\n"
        "Who wants to leave a lasting impression? Drop IMMORTAL!\n\n"
        "Rich, warm, long-lasting.\n"
        "100ml, starting low!"
    ),
    61: (
        "Ana Abiyedh ROUGE!\n"
        "Ana Abiyedh means 'I am white' — this is the RED edition.\n"
        "Red fruits + warm musks = AMAZING.\n\n"
        "Sweet, warm, inviting. Unisex versatility.\n"
        "60ml, starting low!"
    ),
    63: (
        "Yara ELIXIR — the CONCENTRATED Yara!\n"
        "If regular Yara is a 10, this is a HUNDRED.\n"
        "Yara fans, are you ready?!\n\n"
        "Deeper, richer, longer lasting than the original.\n"
        "Everything you love about Yara, turned up to MAX.\n"
        "100ml, starting LOW!"
    ),
    64: (
        "Lattafa Nebras — the LANTERN!\n"
        "A guiding light fragrance — warm, inviting, beautiful.\n"
        "Who here is looking for their signature scent? This could be IT.\n\n"
        "Warm amber glow. Comforting and magnetic.\n"
        "100ml unisex, starting low!"
    ),
    67: (
        "Yara Moi — the SOPHISTICATED Yara!\n"
        "If Yara is the fun younger sister, Moi is the elegant older one.\n"
        "Which are YOU? Tell me in the chat!\n\n"
        "Floral, fruity, gourmand — long lasting formula.\n"
        "100ml full size, starting low!"
    ),
    68: (
        "Lattafa Mayar for Women!\n"
        "Ladies, who wants something soft and elegant?\n\n"
        "Soft, floral, powdery with a warm vanilla finish.\n"
        "The kind of scent that makes people say 'you smell BEAUTIFUL.'\n"
        "100ml, starting low!"
    ),
    69: (
        "RASASI HAWAS — the ORIGINAL!\n"
        "Hawas means DESIRE — and EVERYONE desires this scent!\n"
        "Who's heard of Hawas? It's LEGENDARY!\n\n"
        "Aquatic, fresh, citrusy with warm amber base.\n"
        "One of the BEST aquatic fragrances on the market.\n"
        "100ml EDP, BEAST mode longevity. Starting low!"
    ),
    72: (
        "Jean Lowe VIBE!\n"
        "Good vibes ONLY! Who's vibing tonight?!\n\n"
        "Citrus, fruity, aromatic, woody — energetic and fresh.\n"
        "Modern, clean, versatile.\n"
        "Starting low!"
    ),

    # ── Jovan ──────────────────────────────────────────────────────
    111: (
        "Jovan Musk for Women — a CLASSIC!\n"
        "This has been around for DECADES and it STILL hits.\n"
        "Who's grandma wore this? Who's mom wore this? Be honest!\n\n"
        "Clean, warm, musky — the original crowd-pleaser.\n"
        "Timeless, iconic. Starting low!"
    ),

    # ── Nautica ────────────────────────────────────────────────────
    71: (
        "NAUTICA VOYAGE!\n"
        "One of the BEST-SELLING men's fragrances of ALL TIME.\n"
        "Guys, who already owns this? If you don't, WHAT ARE YOU DOING?!\n\n"
        "Fresh, aquatic, green apple and water lotus.\n"
        "THE ultimate summer fragrance — compliments GUARANTEED.\n"
        "3.3 oz bottle. Starting low!"
    ),

    # ── RASASI ─────────────────────────────────────────────────────
    130: (
        "RASASI Hawas ICE — the COOL version!\n"
        "If Hawas is fire, Hawas Ice is the COOLDOWN.\n"
        "Who wants something fresh and icy? Drop ICE!\n\n"
        "Fresh, aquatic, cool mint twist.\n"
        "Perfect summer scent, incredible performance.\n"
        "100ml EDP, starting low!"
    ),

    # ── Armaf Le Femme ─────────────────────────────────────────────
    118: (
        "Le Femme by Armaf!\n"
        "Ladies, Armaf made this one just for YOU.\n"
        "Who loves a feminine floral? Raise your hand in chat!\n\n"
        "Floral, sweet, elegant — beautiful women's fragrance.\n"
        "Great projection, solid longevity.\n"
        "3.4 oz, starting low!"
    ),

    # ── Al Rehab (small bottles / oils) ──────────────────────────
    5: (
        "Al Rehab Sara — 50ml EDP!\n"
        "Ladies, who's named Sara? Shoutout to all the Saras!\n\n"
        "Beautiful feminine fragrance — soft, floral, elegant.\n"
        "Al Rehab has been making fragrances in Saudi Arabia for DECADES.\n"
        "50ml, starting low!"
    ),
    6: (
        "Choco Musk MARSHMALLOW — perfume oil!\n"
        "Chocolate + marshmallow — who's hungry?! Drop YUM!\n\n"
        "This is CONCENTRATED oil — no alcohol, lasts ALL DAY.\n"
        "6ml roller fits in your pocket or purse.\n"
        "Starting low!"
    ),
    7: (
        "Al Rehab CUPCAKE — 100ml EDP!\n"
        "Who loves cupcakes?! What's your favorite flavor? Tell me!\n\n"
        "Smells like a fresh-baked cupcake — vanilla, frosting, sweetness.\n"
        "If you love gourmand scents, this is HAPPINESS.\n"
        "100ml, starting low!"
    ),
    8: (
        "Al Rehab Diwan — 6ml roll-on oil!\n"
        "Royal and elegant — concentrated perfume oil.\n"
        "Warm, rich, oriental.\n\n"
        "Perfect pocket-sized luxury.\n"
        "Starting low!"
    ),
    9: (
        "Choco Musk PISTACHIO oil!\n"
        "Chocolate + pistachio — who's a pistachio lover?!\n"
        "Drop PISTACHIO if that's your favorite nut!\n\n"
        "Sweet, nutty, chocolatey — a dessert for your skin.\n"
        "6ml roller, starting low!"
    ),
    10: (
        "THE ORIGINAL Choco Musk — 6ml oil!\n"
        "This is one of the BEST-SELLING perfume oils in the WORLD.\n"
        "Who's tried it before? How many bottles have you gone through?\n\n"
        "Chocolate and musk — warm, sweet, ADDICTIVE.\n"
        "6ml roller, starting low!"
    ),
    11: (
        "Spanish Vanilla roll-on oil!\n"
        "Vanilla lovers, ASSEMBLE! Type VANILLA!\n\n"
        "Creamy, warm, Spanish vanilla — pure comfort.\n"
        "Unisex, lasts forever on skin.\n"
        "6ml roller, starting low!"
    ),
    12: (
        "Jourie by Al Rehab — 6ml oil!\n"
        "Delicate, beautiful floral — rose, jasmine, soft musk.\n"
        "Who loves florals? This is elegant and feminine.\n\n"
        "6ml roller, starting low!"
    ),
    14: (
        "Choco Musk Marshmallow — FULL SIZE 100ml spray!\n"
        "The spray version! Now you can REALLY layer it on.\n"
        "Chocolate, musk, fluffy marshmallow.\n\n"
        "Who wants to smell like a s'more? Starting low!"
    ),
    15: (
        "Choco Musk Pistachio — 100ml spray!\n"
        "Full size of the beloved Choco Musk Pistachio!\n"
        "If you tried the oil and loved it, HERE'S the big bottle.\n\n"
        "Chocolate, pistachio, warm musk. Starting low!"
    ),
    16: (
        "Spanish Vanilla EDP spray!\n"
        "The spray version of the iconic oil.\n"
        "Warm, creamy vanilla — crowd-pleasing.\n\n"
        "Who's adding this to the vanilla collection? Starting low!"
    ),
    17: (
        "Choco Musk 100ml SPRAY!\n"
        "The world-famous Choco Musk in a FULL SPRAY bottle!\n"
        "How many of you already own the oil version? Tell me!\n\n"
        "Now spray this legendary scent everywhere.\n"
        "Starting low!"
    ),
    18: (
        "FRENCH COFFEE by Al Rehab!\n"
        "Coffee addicts, this one's for YOU!\n"
        "How many cups of coffee did you have today? Drop the number!\n\n"
        "Rich, roasted, warm — smells like a French cafe.\n"
        "100ml, starting low!"
    ),
    19: (
        "Al Rehab OVERDOSE — intense and POWERFUL!\n"
        "Not for the faint-hearted! Who wants something BOLD?\n\n"
        "Warm, oriental, unapologetic.\n"
        "100ml EDP, starting low!"
    ),
    20: (
        "Pink Breeze — soft, pink, breezy!\n"
        "Who loves pastel vibes? This is that scent.\n\n"
        "Light, feminine, fresh — spring and summer perfection.\n"
        "50ml, starting low!"
    ),
    21: (
        "Al Rehab Blue — fresh and clean!\n"
        "Simple, crisp, refreshing.\n"
        "Who needs a no-fuss everyday scent? THIS.\n\n"
        "50ml, starting low!"
    ),
    22: (
        "Choco Musk 50ml spray — travel friendly!\n"
        "Perfect size for your bag or gym locker.\n"
        "Same amazing scent, mid-size bottle.\n\n"
        "Starting low!"
    ),
    23: (
        "Al Rehab Dhikra — means MEMORY in Arabic!\n"
        "What's your favorite scent memory? Share in the chat!\n\n"
        "Warm, oriental, sweet and woody.\n"
        "50ml, starting low!"
    ),
    24: (
        "Choco Musk Pistachio 50ml — mid-size!\n"
        "Perfect for trying before getting the big bottle.\n"
        "Chocolate, pistachio, musk — you already know.\n\n"
        "Starting low!"
    ),
    25: (
        "Love Apple — sweet and fruity!\n"
        "Who loves apple scents? Drop an APPLE!\n\n"
        "Fun, playful, totally addictive.\n"
        "50ml unisex, starting low!"
    ),
    26: (
        "Allure of Oud — 35ml spray!\n"
        "Rich, warm, authentic oud in a compact bottle.\n"
        "Al Rehab KNOWS oud — this is the real deal.\n\n"
        "Starting low!"
    ),
    27: (
        "Royal Men by Al Rehab!\n"
        "Gentlemen, who wants to feel ROYAL tonight?\n\n"
        "Bold, masculine, refined. Woody and aromatic.\n"
        "50ml, starting low!"
    ),
    28: (
        "Million Secrets — for the ladies!\n"
        "Every woman has secrets — this one smells AMAZING.\n"
        "Sweet, floral, elegant.\n\n"
        "50ml, starting low!"
    ),
    29: (
        "Ocean Breeze — fresh ocean vibes!\n"
        "Close your eyes, you're at the BEACH.\n"
        "Who misses the ocean? Drop a WAVE!\n\n"
        "Clean, aquatic, refreshing. 50ml, starting low!"
    ),
    30: (
        "Al Rehab Ameer — means PRINCE!\n"
        "Who's the prince in the chat tonight?!\n\n"
        "Royal elegance — warm, woody, oriental.\n"
        "50ml, starting low!"
    ),
    33: (
        "London Girl by Al Rehab!\n"
        "Any London fans in here? Drop your favorite city!\n\n"
        "Modern, chic, fresh and feminine.\n"
        "Starting low!"
    ),
    34: (
        "Atheer Al Layl — ESSENCE of the NIGHT!\n"
        "Night owls, this is YOUR scent!\n"
        "When do you like wearing fragrance most — day or night? Tell me!\n\n"
        "Dark, mysterious, warm — evening signature.\n"
        "100ml, starting low!"
    ),
    31: (
        "Marine Spirit — fresh OCEAN vibes!\n"
        "Who loves aquatic scents? Clean, fresh, easy to wear.\n\n"
        "Your go-to everyday scent.\n"
        "100ml, starting low!"
    ),
    32: (
        "Bissan by Al Rehab — 100ml EDP!\n"
        "Warm, floral, soft musky base.\n"
        "A beautiful everyday fragrance with Arabian roots.\n\n"
        "Who appreciates classic Arabian perfumery? Starting low!"
    ),
    13: (
        "Diala Perfume OIL — only 6ml but SUPER concentrated!\n"
        "This is PURE fragrance — no alcohol, just scent.\n"
        "Sweet, creamy, charming floral.\n\n"
        "Perfume oils sit close to your skin — it's YOUR secret.\n"
        "Fits in your purse or pocket. Starting low!"
    ),

    # ── Generic ────────────────────────────────────────────────────
    73: (
        "Alright, we've got a mystery fragrance here!\n"
        "Who likes surprises?! Let me tell you about this one.\n"
        "Starting it low, who's feeling lucky?!"
    ),
}


def main():
    raise SystemExit(LEGACY_SQLITE_RETIRED)


if __name__ == "__main__":
    main()
