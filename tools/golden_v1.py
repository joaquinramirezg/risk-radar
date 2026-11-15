"""Golden set v1 for Ask the filings, written by Claude (claude-opus-5-5) on Nov 15 2026
at Joaquin's instruction ("run it yourself"), from 51 risk factors sampled one per company
(seed 2026, weighted toward changed risks). Questions are paraphrased in plain words so
they do not copy the filing's vocabulary. Gold sentence ids are 0-based."""
import json
from pathlib import Path

A = "claude-opus-5-5"
Q = [
 ("AAPL.fd90cfb2dc9d", "Why might Apple's share price fall even if the business is doing fine?", [1, 5], "Apple says the whole market sometimes swings for reasons unrelated to a company's results, and its stock could drop sharply if it misses expectations on growth, profit, dividends or buybacks."),
 ("ORCL.c9049a92988b", "Why are Oracle's quarterly results hard to predict?", [1, 3, 4], "Many big software and hardware deals close late in the quarter, a few large deals drive results, and delays in its cloud infrastructure buildout affect cloud revenue forecasts."),
 ("KO.a12ea7e11d51", "Does Coca-Cola think government focus on childhood chronic disease could hurt sales?", [1, 2], "Yes. It points to recent US federal and state initiatives on drivers of childhood chronic disease and public concern about sweetened drinks as threats to demand."),
 ("NKE.e4c276b7e505", "What tricks do hackers use against Nike, according to its annual report?", [1], "Increasingly sophisticated attackers using social engineering such as phishing and large automated attacks that can go undetected for long periods."),
 ("DUK.231e73eb6d5a", "What happens to Duke Energy if its planned deals and asset sales fall through?", [3, 4, 5], "It may have to find other funding for its capital plan instead of displacing planned debt and stock issuance, its credit metrics and ratings could suffer, and markets could react badly."),
 ("BAC.65621ffe9945", "Which kinds of natural disasters does Bank of America say could disrupt its operations?", [6], "Earthquakes and weather events such as wildfires, tornadoes, hurricanes and floods."),
 ("GE.c44a63ca094d", "Is GE Aerospace worried about restrictions on rare earth minerals?", [2], "Yes. It lists export controls, including restrictions on rare earth minerals, among the policy shifts that could interfere with its operations and supply chain."),
 ("TSLA.12f24c8cd62d", "Which privacy laws does Tesla name as risks?", [3, 4], "The EU's General Data Protection Regulation and the California Consumer Privacy Act, plus other state and Asia-Pacific laws."),
 ("GM.0ce9643c63cb", "How is General Motors trying to soften the blow from tariffs, and will it work?", [6], "By changing its US production plan and reducing or pausing some imports; GM says these steps may not succeed and will not fully offset the tariffs."),
 ("GM.0ce9643c63cb", "Which trade agreement review could change the tariffs GM pays?", [1], "The ongoing review of the US-Mexico-Canada Agreement."),
 ("ISRG.986f29354f7d", "What can the FDA do if Intuitive Surgical fails to report problems with its robots?", [4], "Take action including warning letters, administrative actions, criminal prosecution and civil penalties."),
 ("CHTR.e61b7396bb51", "Has Charter ever had a cyberattack that caused a major data leak?", [5], "No. Charter says attempts to access its network have not yet resulted in any material release of information or disruption."),
 ("BA.978d06be1e99", "Which government agencies audit Boeing's defense contract costs?", [0], "The Defense Contract Audit Agency and the Defense Contract Management Agency."),
 ("DIS.c28b5c565e8f", "What credit ratings does Disney report from Moody's and S&P?", [2], "As of September 27, 2025: Moody's A2 long-term and P-1 short-term; S&P A long-term and A-1 short-term, both stable."),
 ("BMY.0239e63e6c4f", "Until when does Bristol Myers Squibb get US tariff relief?", [4], "Until January 2029, under its agreement with the US government."),
 ("BMY.0239e63e6c4f", "Why is making CAR-T therapies a supply risk for Bristol Myers?", [6, 7], "The manufacturing processes for these cell therapies are still evolving and may be more complicated or costly, and sourcing raw materials and building reliable processes and distribution affects costs."),
 ("CMCSA.033de0b027c8", "Why are cable distributors less willing to carry Comcast's TV networks?", [1, 2], "People are watching less linear TV, so network subscribers keep falling, and providers may refuse to carry networks that do not draw enough viewers or offer worse terms."),
 ("JPM.cacc0b402e31", "What could force JPMorgan to hold more capital?", [1, 2, 3], "Regulator actions or rule changes, balance sheet changes that raise risk-weighted assets, and higher stress losses estimated by the Federal Reserve."),
 ("UNH.0b38e9010a93", "Why could doctors and hospitals hurt UnitedHealth's business?", [4, 5], "Providers could refuse to contract, demand higher payments, and large hospital and physician groups have market power that weakens UnitedHealth's bargaining position."),
 ("GOOGL.837fee4b47fd", "Does Alphabet say its AI features create new security risks?", [5], "Yes. Features that rely on AI may face unanticipated security threats as understanding of AI-centric security risks develops."),
 ("MRK.e06702fd5177", "What makes selling in emerging markets risky for Merck?", [2, 4, 5], "Some of those countries are vulnerable to financial instability and have little to spend on health care, Merck may rely more on third-party agents, and their currencies can devalue."),
 ("SBUX.c59003bc94e4", "Are all of Starbucks' trademarks registered everywhere it operates?", [2], "No. Not all of its trademarks are registered in every market, and some may never be."),
 ("PM.2ab11db2582e", "What does Philip Morris say some smoke-free product competitors are doing wrong?", [4], "Some alienate consumers from innovative products with inappropriate marketing and inferior products that lack scientific substantiation."),
 ("ABT.d96ee7ac7916", "Is Abbott seeing pressure on its prices?", [0], "Yes. Its businesses have experienced downward pressure on some product prices in the US and other countries."),
 ("HD.6471ea7dac73", "Is Home Depot mostly self-insured?", [0], "Yes. It is predominantly self-insured for risks like general and product liability, property loss, workers' compensation and employee medical."),
 ("QCOM.49a9d44d2ce5", "Beyond phones, which markets does Qualcomm need to grow into?", [6], "Automotive, IoT and data center."),
 ("LOW.300ebb4f5712", "Has Lowe's faced social media backlash, and over what?", [8], "Yes, criticism in the media and negative social media campaigns over initiatives including diversity and inclusion and changes to them."),
 ("NOW.c3968421007d", "Could missing its sustainability goals hurt ServiceNow?", [1, 4], "Yes. Failing or seeming to fail its sustainability goals could harm its reputation, and damage to its brand may reduce demand."),
 ("GILD.38ffcb62452e", "Which Gilead cancer trial missed its main goal on overall survival?", [4], "The Phase 3 EVOKE-01 study of sacituzumab govitecan in previously treated metastatic non-small cell lung cancer, announced January 2024."),
 ("BKNG.57531722ed89", "Why is expanding in China hard for Booking Holdings?", [7], "Local requirements may restrict participation by foreign businesses, making entry and expansion costly, difficult or impossible."),
 ("TMUS.cb3525ea0ced", "Does T-Mobile face lawsuits over health effects of phones?", [2], "Yes. It and other carriers and manufacturers face current and potential lawsuits alleging adverse health effects from wireless handsets and transmissions."),
 ("COF.1925b6250cf3", "Why is Capital One on the hook when a merchant goes bankrupt after a card sale?", [2, 3, 4], "It is contingently liable for disputed card transactions; if a dispute goes the customer's way and it cannot collect from the merchant, Capital One bears the loss."),
 ("GS.4aec74275bc6", "What problems with generative AI models does Goldman Sachs worry about?", [4, 5], "They may produce incorrect output, leak confidential information, or reflect biases, and their complexity makes it hard to understand why they produce an output."),
 ("MSFT.21522c2cd88d", "What datacenter parts has Microsoft had trouble getting?", [4], "Semiconductors, networking equipment, power systems, cooling equipment and other key components."),
 ("TGT.7c8f4a47624e", "Which times of year matter most for Target's sales?", [0, 1], "The November and December holiday period in the fourth quarter, plus back-to-school and back-to-college and other seasonal moments."),
 ("LLY.62e2accf26f6", "Which Eli Lilly drug is about to lose patent protection?", [1], "Trulicity will lose significant patent and remaining data protections in the next few years."),
 ("CSCO.ee4e97257aef", "Why can Cisco's partnerships turn into competition?", [2, 3], "It may compete with a company in some areas while cooperating in others, and successful alliances may increase competition in certain business areas."),
 ("NEE.011c465c0f4d", "What happens if NextEra's computer systems fail or get hacked?", [2], "Sensitive data could be compromised and NextEra and FPL could be unable to fulfill critical business functions."),
 ("CRM.6734e8a96a3c", "Why would a sales slump not show up right away in Salesforce's revenue?", [0, 2], "Revenue is recognized over subscription terms of typically 12 to 36 months, so a drop in new subscriptions hits future quarters rather than the current one."),
 ("JNJ.7388547d3dc7", "Could Johnson & Johnson be barred from government health programs?", [3, 4], "Yes. Government scrutiny can carry civil and criminal penalties including debarment, which could materially hurt the business."),
 ("AXP.1fe2e9cd1859", "What compliance problem did American Express find in its rewards programs?", [2], "It identified issues related to its rewards and benefits programs and has taken actions to fix them and strengthen controls."),
 ("CAT.369599bf039c", "What does Caterpillar need to keep selling its machines?", [2, 3], "Strong dealer relationships, products meeting customers' quality, performance and price expectations, leading-edge innovation and protection of its intellectual property."),
 ("F.ceed9af54d9b", "Why does a small drop in car sales hit Ford hard?", [0], "Ford has a high share of fixed costs, so small changes in industry volume substantially affect cash flow and results."),
 ("BK.36991af48d51", "What new risks does BNY see in digital assets?", [5, 6], "Digital asset products are new to BNY and the industry and may bring unique risks, especially cybersecurity exposures and dependence on third parties."),
 ("BK.36991af48d51", "Is BNY betting on artificial intelligence, and what could go wrong?", [2, 3], "It has devoted significant resources to building AI into its operations and client offerings; if the technology does not perform or deliver efficiencies, its reputation and results could suffer."),
 ("AVGO.498b92ecc7e2", "Does Broadcom have to buy back a set amount of stock?", [3], "No. It is not obligated to repurchase any specific amount, and the program may be suspended or terminated at any time."),
 ("DE.b2766cab6662", "Can hackers take control of John Deere's connected equipment?", [1, 3], "Deere says malicious actors have attempted, and may attempt, to gain unauthorized access to its connected products, and any such access or control could cost it sales and trust."),
 ("UNP.2d770bf90f40", "How long does Union Pacific's fuel surcharge lag behind fuel prices?", [4], "About two months."),
 ("UPS.fef044a8b873", "Which kinds of trade policies affect UPS?", [1, 2], "Tariff and trade policies, export requirements, embargoes, sanctions, taxes and unpredictable trade arrangements between the US and its partners."),
 ("DHR.31d9af601cb5", "What can product defects lead to for Danaher?", [1, 2], "Recalls or safety alerts, removal of products from the market, product liability claims, significant costs and damage to its reputation."),
 ("CVS.0b68db93c375", "Have CVS vendors leaked customers' personal data?", [6], "Yes. Some vendors had incidents that disclosed confidential information, including personal information of members, patients or employees."),
 ("USB.d6a42305f7ef", "Why does U.S. Bancorp now list poor data management as a risk?", [1, 2], "Its data processes can fail through human error, system failure or weak controls, which could hurt data quality and its ability to manage risk and report accurately."),
 ("ADBE.91bc004a02b7", "What can go wrong when Adobe buys another company?", [3, 4, 6], "It may not get the expected benefits, may struggle to integrate operations and people, and a deal may fail to close for lack of regulatory approval."),
 ("NFLX.523ec904e5ee", "What will decide whether Netflix's ad business grows?", [0, 2, 5], "Netflix has limited advertising experience; growth depends on attracting advertisers, competing for ad spend, and other factors like engagement and measurement tools."),
]
UNANSWERABLE = [
 ("Should I buy Nvidia stock right now?", "investment advice; the agent must decline"),
 ("What does Rivian say about tariffs in its risk factors?", "Rivian is not in the S&P 100 set"),
 ("What credit rating does Fitch give Disney?", "Disney's risk factors give Moody's and S&P ratings only"),
 ("How much did Tesla pay in GDPR fines last year?", "risk factors name GDPR but state no fine amounts"),
 ("What was Apple's revenue from China in its last fiscal year?", "a financial figure from the statements, not the risk factors"),
 ("Which S&P 100 company will be hacked next?", "a prediction"),
 ("What is the Coca-Cola CEO's salary?", "compensation is in the proxy statement, not Item 1A"),
 ("What did Spotify add to its risk factors about AI this year?", "Spotify is not in the S&P 100 set"),
 ("How many employees did Boeing lay off in 2026?", "a headcount the risk factors do not state"),
]

out = Path("/Users/joaquinramirez/Documents/Employment/code/sec-10k-retrieval-evals/data/golden/golden.jsonl")
out.parent.mkdir(parents=True, exist_ok=True)
corpus = json.loads(Path("/Users/joaquinramirez/Documents/Employment/code/sec-10k-retrieval-evals/api/_data/corpus.json").read_text())
risks = {r["id"]: r for r in corpus["risks"]}
rows = []
for rid, q, nums, ans in Q:
    assert rid in risks and all(n < len(risks[rid]["sentences"]) for n in nums), rid
    rows.append({"question": q, "gold_risks": [rid], "gold_sentences": [f"{rid}.{n}" for n in nums], "answer": ans, "author": A})
for q, why in UNANSWERABLE:
    rows.append({"question": q, "gold_risks": [], "gold_sentences": [], "answer": "", "note": why, "author": A})
with out.open("w") as fh:
    for k, r in enumerate(rows, 1):
        fh.write(json.dumps({"qid": f"q{k:03d}", **r}, ensure_ascii=False, sort_keys=True) + "\n")
print(len(rows), "rows", sum(1 for r in rows if not r["gold_risks"]), "unanswerable")
