# Dataset Access Request Drafts

Prepared at the user's request, October 11, 2026. These drafts have not been
sent. Replace identity/affiliation fields truthfully; no academic identity,
access grant, classroom redistribution permission or budget is assumed.

## Coach-refined assessments: TAGS / Tennis Action-GE

[Wang et al., ICCV Workshops 2025](https://openaccess.thecvf.com/content/ICCV2025W/AMFG/html/Wang_Generating_Tennis_Action_Instruction_Based_on_a_Large_Language_Model_ICCVW_2025_paper.html)
describes coach-refined tennis evaluations. No downloadable data/license was
located. The [primary PDF](https://openaccess.thecvf.com/content/ICCV2025W/AMFG/papers/Wang_Generating_Tennis_Action_Instruction_Based_on_a_Large_Language_Model_ICCVW_2025_paper.pdf)
lists first author Zhiyuan Wang's address as **zhiy.wang@seu.edu.cn** (verified
October 11, 2026). This is a proposed recipient, not evidence that the address
is monitored or that access will be granted.

Subject: Request for licensed serve/Trophy Pose subset and coach annotations

Dear authors,

I am [full name], working with [school/institution or truthful affiliation] on
TennisPose, a student project that analyzes a single tennis-serve preparation
photo locally with MediaPipe and Python. We are seeking independent coaching
labels rather than interpreting model estimates as ground truth.

Would you be willing to provide a small licensed subset of the Tennis Action-GE
dataset covering serves, especially correct and deliberately incorrect Trophy
Pose arm positions? We would appreciate the original RGB clips or approved
still frames, coach-refined assessments, any frame/stage annotations, anonymous
player/session identifiers, and the annotation rubric or coach agreement data.

Could you clarify whether each label concerns the visible Trophy checkpoint or
the entire serve, and whether the 3D joints are estimated or independently
measured? If measured, please include joint-center definitions, coordinate
units, camera synchronization/calibration and the elbow-angle convention.

Our immediate purposes are local student evaluation and teaching. Please state
whether classroom display, extracting stills, storing a local teaching subset,
competition demonstrations, and redistributing attributed examples in a public
repository are permitted. Please also clarify any restriction concerning
fee-based teaching. We can keep raw data outside Git if redistribution is not
allowed. We would preserve required citations and obtain explicit permission
before any use beyond the granted license.

We are not requesting external inference services or permission to make medical
or injury-prevention claims. A small subset and clear terms would be sufficient
for initial validation.

Thank you,
[full name]
[truthful affiliation]
[contact email]

## Paired multi-view and 3D: SportsPose

The [official access page](https://christianingwersen.github.io/SportsPose/download.html)
lists **cmomi@dtu.dk** and requires name, academic affiliation, academic email
and intended use. Its present terms are academic-only and nontransferable;
ordinary access does not authorize bundling the raw dataset for students.
Use this draft only if the sender has a real qualifying academic affiliation,
or first ask whether another license is available.

Subject: SportsPose tennis subset access and classroom-use permission inquiry

Dear Christian Mikkelstrup,

My name is [full name], affiliated with [actual academic institution]. My
academic email address is [actual academic email]. We are developing TennisPose,
a local Python/Streamlit student project for measuring a racket-arm elbow angle
from one tennis-serve preparation image.

Our intended use is to evaluate the photo estimator against synchronized
multi-view/independent 3D references. We request the smallest tennis subset that
includes arm preparation and serves, RGB frames, camera calibration and
synchronization, 3D joint definitions, and any marker-validation or phase labels.
Could you identify which reference joints are independently measured and which
are reconstructed, including the uncertainty of the arm joint centers?

We understand the current academic license is personal and nontransferable.
Please clarify whether classroom viewing, derived plots/angle tables, extracting
attributed stills, competition demos, or publishing a small teaching example set
is allowed. We will not share raw data or grant students access under another
person's license without specific permission. If these uses require a different
license, please describe the available terms before any download.

We will cite the required SportsPose paper and use a player/session-separated
evaluation protocol. No private student images will be supplied to the dataset
provider, and no cloud deployment is planned.

Thank you,
[full name]
[academic affiliation]
[academic email]
