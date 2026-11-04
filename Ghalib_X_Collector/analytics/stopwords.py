"""Arabic and English stop words (normalised forms, see processing.cleaning.normalize_arabic)."""
from processing.cleaning import normalize_arabic

_AR = """
في من على الى إلى عن مع هذا هذه ذلك تلك هو هي هم هن انا أنا انت أنت نحن انتم كان كانت يكون تكون
ان أن إن او أو ثم بل لا لم لن ما ماذا لماذا كيف متى اين أين اي أي كل بعض غير بين عند عندما حتى قد
لقد كما لكن لكنه الذي التي الذين اللذين اللتين اللاتي اللواتي هناك هنا ايضا أيضا جدا فقط منذ خلال
بعد قبل حول ضد دون تحت فوق امام أمام وراء يا و ف ب ل ك به بها بهم له لها لهم منه منها فيه فيها عليه
عليها اليه إليه اليها إليها عنه عنها هل إذا اذا لو لولا كلما ليس ليست صار اصبح أصبح مازال ما زال
اللي ايش وش شو مو مش يعني بس كذا كده هيك والله الله اله عشان علشان لان لأن انه أنه انها أنها
يوم اليوم الان الآن كذلك وهو وهي وفي ومن وعلى والى وإلى وكان وقد ولا ولم وما فى الي علي
""".split()
_EN = """
a an the and or but if then else of to in on at by for with from as is are was were be been being
this that these those it its it's i me my we our you your he him his she her they them their what which
who whom whose when where why how all any both each few more most other some such no nor not only own
same so than too very s t can will just don should now rt via amp https http co www com do does did
have has had having am up down out over under again further once here there about into through during
before after above below off would could also us get got like one new
""".split()

STOPWORDS = {normalize_arabic(w).lower() for w in _AR + _EN}
