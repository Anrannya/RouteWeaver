# -*- coding: utf-8 -*-
"""Hand-authored v2-style knowledge for the REST of the CSQA training split
(i.e. every train_rand_split question that is NOT one of the 200 evaluation
questions in TmpRes/step2In_csqa_last.json).

Authored directly by reading each question stem + options ONLY. The gold
answerKey was never consulted. Each entry mimics the v2 KB style: a short,
standalone, decontextualized commonsense fact expressing a functional /
causal / locational / purpose / property relation (no bare dictionary
definitions).

Format:  KNOWLEDGE_REST[qid] = [(option_label, dimension, fact), ...]
1-2 facts per question. dimension must be in ALLOWED_DIMENSIONS
(see build_rest_kb.py). option_label must be a real option of that question.

This file GROWS batch by batch. build_rest_kb.py is idempotent: it only
adds packs for qids present here and not yet written, then rebuilds the flat
retriever KB from both the original 200-question pack and this rest pack.
"""

from rest_kb_data_320_519 import KNOWLEDGE_REST_320_519
from rest_kb_data_520_619 import KNOWLEDGE_REST_520_619
from rest_kb_data_620_719 import KNOWLEDGE_REST_620_719
from rest_kb_data_720_919 import KNOWLEDGE_REST_720_919
from rest_kb_data_920_1019 import KNOWLEDGE_REST_920_1019
from rest_kb_data_1020_1119 import KNOWLEDGE_REST_1020_1119
from rest_kb_data_1120_1319 import KNOWLEDGE_REST_1120_1319
from rest_kb_data_1320_1419 import KNOWLEDGE_REST_1320_1419
from rest_kb_data_1420_1519 import KNOWLEDGE_REST_1420_1519
from rest_kb_data_1520_1619 import KNOWLEDGE_REST_1520_1619
from rest_kb_data_1620_1719 import KNOWLEDGE_REST_1620_1719
from rest_kb_data_1720_1819 import KNOWLEDGE_REST_1720_1819
from rest_kb_data_1820_1919 import KNOWLEDGE_REST_1820_1919
from rest_kb_data_1920_2019 import KNOWLEDGE_REST_1920_2019
from rest_kb_data_2020_2119 import KNOWLEDGE_REST_2020_2119
from rest_kb_data_2120_2219 import KNOWLEDGE_REST_2120_2219
from rest_kb_data_2220_2319 import KNOWLEDGE_REST_2220_2319
from rest_kb_data_2320_2419 import KNOWLEDGE_REST_2320_2419
from rest_kb_data_2420_2519 import KNOWLEDGE_REST_2420_2519
from rest_kb_data_2520_2619 import KNOWLEDGE_REST_2520_2619
from rest_kb_data_2620_2719 import KNOWLEDGE_REST_2620_2719
from rest_kb_data_2720_2819 import KNOWLEDGE_REST_2720_2819
from rest_kb_data_2820_2919 import KNOWLEDGE_REST_2820_2919
from rest_kb_data_2920_3019 import KNOWLEDGE_REST_2920_3019
from rest_kb_data_3020_3119 import KNOWLEDGE_REST_3020_3119
from rest_kb_data_3120_3219 import KNOWLEDGE_REST_3120_3219
from rest_kb_data_3220_3319 import KNOWLEDGE_REST_3220_3319
from rest_kb_data_3320_3419 import KNOWLEDGE_REST_3320_3419
from rest_kb_data_3420_3519 import KNOWLEDGE_REST_3420_3519
from rest_kb_data_3520_3619 import KNOWLEDGE_REST_3520_3619
from rest_kb_data_3620_3719 import KNOWLEDGE_REST_3620_3719
from rest_kb_data_3720_3819 import KNOWLEDGE_REST_3720_3819
from rest_kb_data_3820_3919 import KNOWLEDGE_REST_3820_3919
from rest_kb_data_3920_4019 import KNOWLEDGE_REST_3920_4019
from rest_kb_data_4020_4119 import KNOWLEDGE_REST_4020_4119
from rest_kb_data_4120_4219 import KNOWLEDGE_REST_4120_4219
from rest_kb_data_4220_4319 import KNOWLEDGE_REST_4220_4319
from rest_kb_data_4320_4419 import KNOWLEDGE_REST_4320_4419
from rest_kb_data_4420_4519 import KNOWLEDGE_REST_4420_4519
from rest_kb_data_4520_4619 import KNOWLEDGE_REST_4520_4619
from rest_kb_data_4620_4719 import KNOWLEDGE_REST_4620_4719
from rest_kb_data_4720_4819 import KNOWLEDGE_REST_4720_4819
from rest_kb_data_4820_4919 import KNOWLEDGE_REST_4820_4919
from rest_kb_data_4920_5019 import KNOWLEDGE_REST_4920_5019
from rest_kb_data_5020_5119 import KNOWLEDGE_REST_5020_5119
from rest_kb_data_5120_5219 import KNOWLEDGE_REST_5120_5219
from rest_kb_data_5220_5319 import KNOWLEDGE_REST_5220_5319
from rest_kb_data_5320_5419 import KNOWLEDGE_REST_5320_5419
from rest_kb_data_5420_5519 import KNOWLEDGE_REST_5420_5519

from rest_kb_data_5520_5619 import KNOWLEDGE_REST_5520_5619
from rest_kb_data_5620_5719 import KNOWLEDGE_REST_5620_5719
from rest_kb_data_5720_5819 import KNOWLEDGE_REST_5720_5819
from rest_kb_data_5820_5919 import KNOWLEDGE_REST_5820_5919
from rest_kb_data_5920_6019 import KNOWLEDGE_REST_5920_6019
from rest_kb_data_6020_6119 import KNOWLEDGE_REST_6020_6119
from rest_kb_data_6120_6219 import KNOWLEDGE_REST_6120_6219
from rest_kb_data_6220_6319 import KNOWLEDGE_REST_6220_6319
from rest_kb_data_6320_6419 import KNOWLEDGE_REST_6320_6419
from rest_kb_data_6420_6519 import KNOWLEDGE_REST_6420_6519
from rest_kb_data_6520_6619 import KNOWLEDGE_REST_6520_6619
from rest_kb_data_6620_6719 import KNOWLEDGE_REST_6620_6719
from rest_kb_data_6720_6819 import KNOWLEDGE_REST_6720_6819
from rest_kb_data_6820_6919 import KNOWLEDGE_REST_6820_6919
from rest_kb_data_6920_7019 import KNOWLEDGE_REST_6920_7019
from rest_kb_data_7020_7119 import KNOWLEDGE_REST_7020_7119
from rest_kb_data_7120_7219 import KNOWLEDGE_REST_7120_7219
from rest_kb_data_7220_7319 import KNOWLEDGE_REST_7220_7319
from rest_kb_data_7320_7419 import KNOWLEDGE_REST_7320_7419
from rest_kb_data_7420_7519 import KNOWLEDGE_REST_7420_7519
from rest_kb_data_7520_7619 import KNOWLEDGE_REST_7520_7619
from rest_kb_data_7620_7719 import KNOWLEDGE_REST_7620_7719
from rest_kb_data_7720_7819 import KNOWLEDGE_REST_7720_7819
from rest_kb_data_7820_7919 import KNOWLEDGE_REST_7820_7919
from rest_kb_data_7920_8019 import KNOWLEDGE_REST_7920_8019
from rest_kb_data_8020_8119 import KNOWLEDGE_REST_8020_8119
from rest_kb_data_8120_8219 import KNOWLEDGE_REST_8120_8219
from rest_kb_data_8220_8319 import KNOWLEDGE_REST_8220_8319
from rest_kb_data_8320_8419 import KNOWLEDGE_REST_8320_8419
from rest_kb_data_8420_8519 import KNOWLEDGE_REST_8420_8519
from rest_kb_data_8520_8619 import KNOWLEDGE_REST_8520_8619
from rest_kb_data_8620_8719 import KNOWLEDGE_REST_8620_8719
from rest_kb_data_8720_8819 import KNOWLEDGE_REST_8720_8819
from rest_kb_data_8820_8919 import KNOWLEDGE_REST_8820_8919
from rest_kb_data_8920_9019 import KNOWLEDGE_REST_8920_9019
from rest_kb_data_9020_9119 import KNOWLEDGE_REST_9020_9119
from rest_kb_data_9120_9219 import KNOWLEDGE_REST_9120_9219
from rest_kb_data_9220_9319 import KNOWLEDGE_REST_9220_9319
from rest_kb_data_9320_9419 import KNOWLEDGE_REST_9320_9419
from rest_kb_data_9420_9519 import KNOWLEDGE_REST_9420_9519
from rest_kb_data_9520_9619 import KNOWLEDGE_REST_9520_9619
from rest_kb_data_9620_9719 import KNOWLEDGE_REST_9620_9719
from rest_kb_data_9720_9740 import KNOWLEDGE_REST_9720_9740

KNOWLEDGE_REST = {
    # ---- batch 1: qids 200-239 ----
    200: [("A", "primary_function", "Talking to someone is a way of communicating and sharing information with others.")],
    201: [("A", "typical_location", "A hair salon is a workplace where hair is styled and accessories such as hairpins are used.")],
    202: [("D", "typical_location", "Players are the people who go onto a football field to take part in the game.")],
    203: [("D", "capability", "A master of a craft has spent years learning and practicing it to reach a high level of skill.")],
    204: [("E", "effect", "Watching television without accomplishing anything results in time being wasted.")],
    205: [("C", "typical_location", "A wild fox is normally seen outside in natural surroundings such as woods and fields.")],
    206: [("E", "property", "Strong feelings such as compassion describe a deep emotional attitude a person holds toward others.")],
    207: [("E", "property", "Calculations that get the details wrong are inaccurate.")],
    208: [("D", "motivation", "People typically have lunch in the middle of the day to satisfy hunger.")],
    209: [("B", "motivation", "Studying the exhibits at a museum is done to gain knowledge.")],
    210: [("B", "effect", "Having an embarrassing situation told to many people can cause emotional distress.")],
    211: [("D", "primary_function", "An electric refrigerator is powered by an electric motor and is found in almost every house.")],
    212: [("C", "typical_location", "Peanut butter is commonly stored in a pantry.")],
    213: [("B", "typical_location", "Families commonly play board games together at home.")],
    214: [("E", "property", "A garage is used to shelter a car, which is an expensive purchase.")],
    215: [("B", "capability", "Humans have the distinctive ability to stand and walk upright on two legs.")],
    216: [("D", "motivation", "Friends often go to see a movie together to spend a quiet evening.")],
    217: [("B", "capability", "A tired animal is likely to lie down in order to rest.")],
    218: [("C", "typical_location", "A race track is a venue with seating where four-legged animals such as horses compete.")],
    219: [("D", "typical_location", "A lemur lives in natural outdoor habitats such as forests and open fields.")],
    220: [("E", "typical_location", "Office supply stores such as Office Depot sell pencils and other stationery.")],
    221: [("B", "property", "Wood becomes shiny enough to show a reflection once it has been polished.")],
    222: [("E", "effect", "Tripping and getting hurt in front of a crowd commonly causes embarrassment.")],
    223: [("D", "typical_location", "A public park contains open areas and courts where people arrange to meet.")],
    224: [("D", "primary_function", "A vegetable garden is planted so that vegetables can be harvested and eaten.")],
    225: [("C", "typical_location", "Outdoor basketball courts are commonly located in public parks.")],
    226: [("E", "used_for", "A balalaika is a stringed musical instrument used to perform music in an ensemble.")],
    227: [("C", "property", "Older homes such as Victorian houses often have attics that accumulate historical items.")],
    228: [("C", "typical_location", "Jackson is the capital of Mississippi, where the state governor's office is located.")],
    229: [("B", "typical_location", "Albums are recorded in a recording studio, where a microphone boom holds the microphone.")],
    230: [("A", "effect", "The most severe possible outcome of an injury is that it causes death.")],
    231: [("A", "property", "Someone who loves their television tends to feel attached to its remote control.")],
    232: [("A", "capability", "Passengers on a bus occupy the seats by sitting down.")],
    233: [("D", "property", "Cards that are wrongly assumed to be common can actually turn out to be rare and valuable.")],
    234: [("D", "effect", "Being asked to end a marriage commonly causes feelings of grief.")],
    235: [("B", "effect", "Looking up at the vast night sky can make a person feel small and insignificant.")],
    236: [("D", "typical_location", "Canada borders the USA, so an apple grown there is an imported product when sold in the USA.")],
    237: [("B", "motivation", "Doing a crossword puzzle is a simple way to pass the time.")],
    238: [("B", "property", "Making the learning process fun can help engage someone who dislikes learning.")],
    239: [("B", "has_prerequisite", "Teaching children in school requires a great deal of patience.")],
    # ---- batch 2: qids 240-279 ----
    240: [("C", "effect", "Proper nail grooming avoids cutting the quick and typically does not cause injury.")],
    241: [("D", "motivation", "Clean clothes help create an attractive appearance when preparing for a date.")],
    242: [("C", "motivation", "Comparing airline and hotel prices is typically done when planning to go on vacation.")],
    243: [("C", "effect", "Lotion is applied to keep skin smooth and moisturized.")],
    244: [("B", "effect", "Eating breakfast in bed as a leisure treat commonly brings pleasure.")],
    245: [("C", "motivation", "An adult man dresses himself as part of getting ready for work.")],
    246: [("B", "typical_location", "An apple tree surrounded by other trees is likely in the woods.")],
    247: [("A", "typical_location", "When tidying a house, a loose dictionary is commonly placed on a shelf.")],
    248: [("B", "effect", "A judge's passing sentence can condemn a guilty person to incarceration.")],
    249: [("C", "typical_location", "A cow bought for work rather than meat is typically taken to a dairy farm.")],
    250: [("C", "motivation", "Bored children often play tag to pass the time.")],
    251: [("D", "typical_location", "Canned goods are often stored behind the small doors of a kitchen cupboard.")],
    252: [("D", "effect", "A relaxing massage on vacation commonly brings great pleasure.")],
    253: [("C", "typical_location", "A department store in a big city reaches the largest pool of potential customers.")],
    254: [("D", "typical_location", "A toy store is a good place to buy a ball.")],
    255: [("A", "primary_function", "Burning coal or wood is a common chemical reaction used as a heat source.")],
    256: [("B", "typical_location", "A piggy bank holds coins so tightly that getting them out usually requires breaking it.")],
    257: [("E", "typical_location", "A restaurant menu lists available beverages, including whether milk is served.")],
    258: [("B", "capability", "A typical classroom holds no more than about one hundred people.")],
    259: [("C", "typical_location", "When fighting starts, a soldier on active duty mainly sees the battlefield.")],
    260: [("E", "typical_location", "Children commonly play games together in a family room at home.")],
    261: [("D", "effect", "Driving a car for a long time commonly leads to getting tired without causing pain.")],
    262: [("B", "property", "The air inside a house has recently been breathed by only the few people who live there.")],
    263: [("A", "effect", "A company that goes bankrupt is typically liquidated.")],
    264: [("A", "property", "Soccer is played without using hands, and blood is not usually spilled during a soccer game.")],
    265: [("E", "typical_location", "A dog at the front window often barks because someone is at the front door.")],
    266: [("A", "typical_location", "A bus stop sign is a place where people commonly line up to wait.")],
    267: [("D", "motivation", "Working primarily to pay bills is often described as actively making money.")],
    268: [("B", "typical_location", "First violin is a leading position within a symphony orchestra.")],
    269: [("C", "typical_location", "Digital files are commonly stored on a computer.")],
    270: [("A", "primary_function", "A washing machine uses water and soap to clean clothes.")],
    271: [("E", "typical_location", "Honey straight from an apiary is often sold at a farmer's market.")],
    272: [("E", "typical_location", "An attache case is commonly brought to a business meeting.")],
    273: [("D", "primary_function", "Chapter listings on the back of a book help a reader decide whether to read it.")],
    274: [("C", "effect", "A family playing cards together is commonly full of joy and amusement.")],
    275: [("A", "typical_location", "Someone whose spouse cannot drink may go to a neighbor's house for a beer.")],
    276: [("A", "typical_location", "Amsterdam is the capital of the Netherlands, where Fortis bank operates.")],
    277: [("A", "typical_location", "An art room keeps many bottles of glue for crafts and school projects.")],
    278: [("C", "typical_location", "A king traditionally receives an ambassador in the throne room.")],
    279: [("A", "typical_location", "Children sometimes play ball on a concrete street.")],
    # ---- batch 3: qids 280-319 ----
    280: [("E", "effect", "In cartoons, diving off a cliff often ends in a comedic splat on the ground.")],
    281: [("B", "property", "At some parties the men do little besides getting drunk.")],
    282: [("E", "typical_location", "A family with more children typically needs a larger house.")],
    283: [("E", "typical_location", "A special ficus tree is commonly displayed in an arboretum.")],
    284: [("B", "effect", "An applicant missing required qualifications is often worried about rejection.")],
    285: [("E", "effect", "Severe heart palpitations can be a sign that someone may not live much longer.")],
    286: [("E", "effect", "Riding a bike through rough terrain is dangerous and can lead to falling down.")],
    287: [("D", "property", "A document that is not obtuse is written in a clear and understandable way.")],
    288: [("A", "primary_function", "Mail orders deliver purchases straight to a customer's doorstep for convenience.")],
    289: [("A", "effect", "Regular exercise is widely known to promote good health.")],
    290: [("C", "typical_location", "In a formal table setting, a spoon is placed on one side of the plate.")],
    291: [("E", "typical_location", "A note on sheet music indicates the melody to be played.")],
    292: [("A", "effect", "Years of playing tennis can lead to tennis elbow from repetitive strain.")],
    293: [("D", "typical_location", "A parking lot near a roller coaster is at an amusement park.")],
    294: [("A", "primary_function", "A virus primarily infects a person and causes disease.")],
    295: [("C", "typical_location", "Someone who does not want to bake a cake can buy one at a bakery.")],
    296: [("E", "typical_location", "Floors in a synagogue are kept clean for holy religious purposes.")],
    297: [("A", "typical_location", "During a war, bullet projectiles are found on the battlefield.")],
    298: [("E", "property", "A chess game might not always have a queen if that piece has been captured.")],
    299: [("B", "has_prerequisite", "Learning hard concepts generally requires being intelligent and attentive.")],
    300: [("B", "primary_function", "Exercise helps addicts cope by providing a healthy way to expend energy.")],
    301: [("E", "typical_location", "A rooster is commonly heard crowing at sunrise, unlike a night owl active at sunset.")],
    302: [("A", "property", "A classroom is often less interesting to children than a toy store or a game.")],
    303: [("C", "property", "Wealthy customers often prefer simple plain bagels over elaborate toppings.")],
    304: [("B", "primary_function", "A shop typically gives customers a container or bag for their purchases.")],
    305: [("D", "typical_location", "A small knight piece is commonly found on a chess board.")],
    306: [("A", "capability", "Swimming is a practical way to get in shape when no land is nearby.")],
    307: [("C", "effect", "An employee who does a poor job may receive criticism from their boss.")],
    308: [("A", "typical_location", "Imported cabinets bought for their appearance are commonly installed in a kitchen.")],
    309: [("C", "effect", "Two people competing with each other may get into an argument.")],
    310: [("D", "primary_function", "AI machines are widely known for answering questions.")],
    311: [("D", "effect", "Waiting in a queue with loud children in front commonly causes irritation.")],
    312: [("C", "typical_location", "A blowfish living freely on its own is found in the great outdoors.")],
    313: [("A", "typical_location", "A paper notice is commonly left on the front door of a house.")],
    314: [("D", "property", "People who purposefully harm others are exhibiting a cruel trait.")],
    315: [("C", "typical_location", "Bleachers with mitts and a first game refer to a baseball stadium.")],
    316: [("C", "effect", "Eating uncooked chicken commonly causes illness.")],
    317: [("B", "effect", "Washing hands excessively can cause skin irritation.")],
    318: [("A", "motivation", "A person laying on the beach is commonly trying to sun himself.")],
    319: [("A", "typical_location", "A spoiled child's massive playroom is one room among many in a big house.")],
    **KNOWLEDGE_REST_320_519,
    **KNOWLEDGE_REST_520_619,
    **KNOWLEDGE_REST_620_719,
    **KNOWLEDGE_REST_720_919,
    **KNOWLEDGE_REST_920_1019,
    **KNOWLEDGE_REST_1020_1119,
    **KNOWLEDGE_REST_1120_1319,
    **KNOWLEDGE_REST_1320_1419,
    **KNOWLEDGE_REST_1420_1519,
    **KNOWLEDGE_REST_1520_1619,
    **KNOWLEDGE_REST_1620_1719,
    **KNOWLEDGE_REST_1720_1819,
    **KNOWLEDGE_REST_1820_1919,
    **KNOWLEDGE_REST_1920_2019,
    **KNOWLEDGE_REST_2020_2119,
    **KNOWLEDGE_REST_2120_2219,
    **KNOWLEDGE_REST_2220_2319,
    **KNOWLEDGE_REST_2320_2419,
    **KNOWLEDGE_REST_2420_2519,
    **KNOWLEDGE_REST_2520_2619,
    **KNOWLEDGE_REST_2620_2719,
    **KNOWLEDGE_REST_2720_2819,
    **KNOWLEDGE_REST_2820_2919,
    **KNOWLEDGE_REST_2920_3019,
    **KNOWLEDGE_REST_3020_3119,
    **KNOWLEDGE_REST_3120_3219,
    **KNOWLEDGE_REST_3220_3319,
    **KNOWLEDGE_REST_3320_3419,
    **KNOWLEDGE_REST_3420_3519,
    **KNOWLEDGE_REST_3520_3619,
    **KNOWLEDGE_REST_3620_3719,
    **KNOWLEDGE_REST_3720_3819,
    **KNOWLEDGE_REST_3820_3919,
    **KNOWLEDGE_REST_3920_4019,
    **KNOWLEDGE_REST_4020_4119,
    **KNOWLEDGE_REST_4120_4219,
    **KNOWLEDGE_REST_4220_4319,
    **KNOWLEDGE_REST_4320_4419,
    **KNOWLEDGE_REST_4420_4519,
    **KNOWLEDGE_REST_4520_4619,
    **KNOWLEDGE_REST_4620_4719,
    **KNOWLEDGE_REST_4720_4819,
    **KNOWLEDGE_REST_4820_4919,
    **KNOWLEDGE_REST_4920_5019,
    **KNOWLEDGE_REST_5020_5119,
    **KNOWLEDGE_REST_5120_5219,
    **KNOWLEDGE_REST_5220_5319,
    **KNOWLEDGE_REST_5320_5419,
    **KNOWLEDGE_REST_5420_5519,
    **KNOWLEDGE_REST_5520_5619,
    **KNOWLEDGE_REST_5620_5719,
    **KNOWLEDGE_REST_5720_5819,
    **KNOWLEDGE_REST_5820_5919,
    **KNOWLEDGE_REST_5920_6019,
    **KNOWLEDGE_REST_6020_6119,
    **KNOWLEDGE_REST_6120_6219,
    **KNOWLEDGE_REST_6220_6319,
    **KNOWLEDGE_REST_6320_6419,
    **KNOWLEDGE_REST_6420_6519,
    **KNOWLEDGE_REST_6520_6619,
    **KNOWLEDGE_REST_6620_6719,
    **KNOWLEDGE_REST_6720_6819,
    **KNOWLEDGE_REST_6820_6919,
    **KNOWLEDGE_REST_6920_7019,
    **KNOWLEDGE_REST_7020_7119,
    **KNOWLEDGE_REST_7120_7219,
    **KNOWLEDGE_REST_7220_7319,
    **KNOWLEDGE_REST_7320_7419,
    **KNOWLEDGE_REST_7420_7519,
    **KNOWLEDGE_REST_7520_7619,
    **KNOWLEDGE_REST_7620_7719,
    **KNOWLEDGE_REST_7720_7819,
    **KNOWLEDGE_REST_7820_7919,
    **KNOWLEDGE_REST_7920_8019,
    **KNOWLEDGE_REST_8020_8119,
    **KNOWLEDGE_REST_8120_8219,
    **KNOWLEDGE_REST_8220_8319,
    **KNOWLEDGE_REST_8320_8419,
    **KNOWLEDGE_REST_8420_8519,
    **KNOWLEDGE_REST_8520_8619,
    **KNOWLEDGE_REST_8620_8719,
    **KNOWLEDGE_REST_8720_8819,
    **KNOWLEDGE_REST_8820_8919,
    **KNOWLEDGE_REST_8920_9019,
    **KNOWLEDGE_REST_9020_9119,
    **KNOWLEDGE_REST_9120_9219,
    **KNOWLEDGE_REST_9220_9319,
    **KNOWLEDGE_REST_9320_9419,
    **KNOWLEDGE_REST_9420_9519,
    **KNOWLEDGE_REST_9520_9619,
    **KNOWLEDGE_REST_9620_9719,
    **KNOWLEDGE_REST_9720_9740,
}
