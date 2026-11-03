"""
Synthetic knowledge base for the fictional "Nova City Services".
Nothing here describes a real government service - it exists only to exercise the pipeline.
"""

FAQS = [
    {"id": "faq-01", "service": "residency", "title": "Resident permit renewal",
     "body": "Resident permits can be renewed online up to 30 days before expiry. You need a valid passport, a recent photo and your Nova ID. Processing takes 3 working days."},
    {"id": "faq-02", "service": "residency", "title": "Sponsoring family members",
     "body": "A resident earning at least 8,000 NCD a month can sponsor a spouse, children and parents. Submit the family sponsorship form with a tenancy contract and proof of salary."},
    {"id": "faq-03", "service": "residency", "title": "Lost Nova ID card",
     "body": "Report a lost Nova ID card online within 7 days. A replacement card costs 150 NCD and is delivered by courier within 5 working days."},
    {"id": "faq-04", "service": "residency", "title": "Overstay after permit expiry",
     "body": "If a resident permit expires, a grace period of 30 days applies. After the grace period a daily overstay fee of 50 NCD is charged until the permit is renewed."},
    {"id": "faq-05", "service": "driving", "title": "Driving licence renewal",
     "body": "Driving licences are renewed online or at any service centre. An eye test certificate from an approved optician is required. The renewal fee is 120 NCD."},
    {"id": "faq-06", "service": "driving", "title": "Vehicle ownership transfer",
     "body": "To transfer vehicle ownership, both buyer and seller sign the transfer request in the app. The vehicle must pass inspection and have no unpaid fines."},
    {"id": "faq-07", "service": "driving", "title": "Paying traffic fines",
     "body": "Traffic and parking fines can be paid in the Nova City app, at kiosks or at service centres. A 25 percent discount applies if a fine is paid within 30 days."},
    {"id": "faq-08", "service": "driving", "title": "Converting a foreign licence",
     "body": "Holders of licences from approved countries can convert to a Nova City licence without a road test. Bring the original licence, a translation and an eye test certificate."},
    {"id": "faq-09", "service": "general", "title": "Library membership",
     "body": "Library cards are free for residents. Apply online or at any branch with your Nova ID. Members can borrow up to 6 books for 3 weeks."},
    {"id": "faq-10", "service": "general", "title": "Bulk waste collection",
     "body": "Bulk waste such as furniture is collected free of charge. Book a pickup in the app and collection happens within 3 working days."},
    {"id": "faq-11", "service": "general", "title": "Service centre opening hours",
     "body": "Service centres open Monday to Friday from 7:30 to 15:30. The central service centre also opens on Saturday from 8:00 to 12:00."},
    {"id": "faq-12", "service": "general", "title": "Complaints and feedback",
     "body": "Complaints can be filed in the app under Feedback. Every complaint gets a reference number and a response within 5 working days."},
]

# 10-question retrieval eval set: question -> id of the FAQ that answers it.
# Several are paraphrased on purpose so pure keyword overlap is not enough.
EVAL = [
    {"q": "How early can I renew my residence permit?", "expected": "faq-01"},
    {"q": "Can I bring my mother to live with me on my residency?", "expected": "faq-02"},
    {"q": "I lost my ID card, what should I do?", "expected": "faq-03"},
    {"q": "What happens if I stay after my permit expires?", "expected": "faq-04"},
    {"q": "How much does it cost to renew a driving licence?", "expected": "faq-05"},
    {"q": "I sold my car, how do I move it to the buyer's name?", "expected": "faq-06"},
    {"q": "Is there a discount for paying a parking ticket early?", "expected": "faq-07"},
    {"q": "Can I swap my licence from abroad without a driving test?", "expected": "faq-08"},
    {"q": "How many books can I borrow?", "expected": "faq-09"},
    {"q": "When is the service centre open on weekends?", "expected": "faq-11"},
]

# A deliberately ungrounded answer: the grounding guardrail must block it.
UNGROUNDED_CASE = {
    "q": "How much does it cost to renew a driving licence?",
    "context_id": "faq-05",
    "bad_answer": "Renewal is free for everyone over 40 and takes 10 minutes at the airport kiosk.",
}
