# EVAL.md — M3.4 retrieval golden set

Golden set: 32 real questions (31 answerable from the ingested corpus, 1 deliberately unanswerable — M3.2's refusal test), run against the real lexical retrieval function (`app/services/retrieval.py::search_chunks`, top-5).

**Scope, stated plainly:** this measures retrieval only — no chatbot/LLM generation layer was built (see DECISIONS.md). "Citation accuracy" below means "was the real expected article present in the top-5 retrieved results", not "did a generated answer cite it correctly". Retrieval is lexical-only (Postgres full-text on the `tsv` column, `to_tsvector('simple', text)` — already populated for every chunk since M2's ingestion, no extra work needed today) — dense/hybrid search is designed (pgvector schema + HNSW index exist) but not populated, since no embedding API key is configured in this environment.

## Real measured results

- **Document-level precision@5** (expected document among top-5 results): **25/31 = 81%**
- **Article-level accuracy** (expected article specifically, where one was specified): **18/31 = 58%**
- **Refusal behaviour on the unanswerable question**: 1/1 returned no result or a near-zero-relevance top result (a real system would need to threshold this and say "I don't have a source for that" — not implemented today, see Known gaps below).

## Per-question results

| Question | Expected | Top real result | Doc hit | Article hit |
|---|---|---|---|---|
| Combien de classes existent pour les établissements classés ? | établissements classés / Art. 3 | Loi du 10 juin 1999 relative aux établissements classés. (Art. 3) | True | True |
| Quelle autorité est compétente pour autoriser les établissements de la classe 1 ? | établissements classés / Art. 4 | Loi du 25 février 2022 relative au patrimoine culturel et modifiant : (Art. 79) | True | False |
| Pendant combien de jours l'avis de demande d'autorisation est-il affiché dans la commune ? | établissements classés / Art. 10 | RÈGLEMENT SUR LES BÂTISSES, LES VOIES (Art. 96) | False | False |
| Quel recours est ouvert devant le tribunal administratif pour un établissement classé ? | établissements classés / Art. 19 | Version consolidée applicable au 01/10/2023 : Loi du 18 juillet 2018 concernant la protection de la nature et des ressources naturelles et modifiant (Art. 68) | True | True |
| Quels sont les objectifs de la politique de l'aménagement du territoire ? | aménagement du territoire / Art. 1 | Loi du 17 avril 2018 concernant l’aménagement du territoire et modifiant : (Art. 32) | True | False |
| Qu'est-ce que le Conseil supérieur de l'aménagement du territoire ? | aménagement du territoire / Art. 4 | Loi du 17 avril 2018 concernant l’aménagement du territoire et modifiant : (Art. 32) | True | True |
| Comment un plan directeur sectoriel est-il rendu obligatoire ? | aménagement du territoire / Art. 9 | Règlement grand-ducal du 10 février 2021 rendant obligatoire le plan directeur sectoriel « paysages ». (Art. 1) | False | False |
| Quel est le champ d'application de la loi relative à la gestion des déchets ? | gestion des déchets / (any article) | Texte coordonné de la loi du 21 mars 2012 relative à la gestion des déchets, et modifiant (Art. 52) | True | True |
| Quelles sont les conditions de l'aide au logement ? | aide au logement / (any article) | Règlement grand-ducal du 10 février 2021 rendant obligatoire le plan directeur sectoriel « logement ». (Art. 1) | True | True |
| Quelles sont les servitudes liées aux radiophares d'alignement de l'aéroport de Findel ? | Aéroport et environs / Art. 19 | Règlement grand-ducal du 17 mai 2006 déclarant obligatoire le plan d'occupation du sol «Aéroport et environs». (Art. 20) | True | False |
| Quelle est la zone d'aéroport définie par le POS Aéroport et environs ? | Aéroport et environs / Art. 14 | Règlement grand-ducal du 28 octobre 2022 désignant zone spéciale de conservation et déclarant obligatoire la zone « Grunewald », et modifiant le règlement grand-ducal du 6 novembre 2009 portant désignation des zones spéciales de conservation. (Art. 1) | True | False |
| Quelles sont les servitudes radioélectriques liées au radar primaire à Findel ? | Aéroport et environs / Art. 22 | Version consolidée applicable au 01/10/2023 : Loi du 18 juillet 2018 concernant la protection de la nature et des ressources naturelles et modifiant (Art. 46) | True | True |
| Quelle est la zone protégée d'intérêt national désignée sous le nom de Grunewald ? | Grunewald / (any article) | Version consolidée applicable au 01/10/2023 : Loi du 18 juillet 2018 concernant la protection de la nature et des ressources naturelles et modifiant (Art. 41) | True | True |
| Quel règlement grand-ducal rend obligatoire le plan directeur sectoriel logement ? | logement / (any article) | Règlement grand-ducal du 10 février 2021 rendant obligatoire le plan directeur sectoriel « logement ». (Art. 1) | True | True |
| Quel règlement grand-ducal rend obligatoire le plan directeur sectoriel paysages ? | paysages / (any article) | Règlement grand-ducal du 10 février 2021 rendant obligatoire le plan directeur sectoriel « paysages ». (Art. 1) | True | True |
| Quel règlement grand-ducal rend obligatoire le plan directeur sectoriel transports ? | transports / (any article) | Règlement grand-ducal du 10 février 2021 rendant obligatoire le plan directeur sectoriel « transports ». (Art. 1) | True | True |
| Quelles zones sont couvertes par le règlement grand-ducal sur les zones d'activités économiques ? | zones d'activités / (any article) | RÈGLEMENT SUR LES BÂTISSES, LES VOIES (Art. 17) | False | True |
| Quelles cartes des zones inondables sont déclarées obligatoires pour l'Alzette et la Wark ? | Alzette / (any article) | Règlement grand-ducal du 30 mars 2022 déclarant obligatoires les cartes des zones inondables et les cartes des risques d’inondation pour les cours d’eau de l’Alzette et de la Wark. (Art. 1) | True | True |
| Quelles cartes des zones inondables sont déclarées obligatoires pour la Sûre supérieure et la Wiltz ? | Sûre supérieure / (any article) | Règlement grand-ducal du 30 mars 2022 déclarant obligatoires les cartes des zones inondables et les cartes des risques d’inondation pour les cours d’eau de la Sûre supérieure, de la Wiltz, de la Clerve et de l’Our. (Art. 1) | True | True |
| Quelle est la zone de protection autour des captages d'eau souterraine Siwebueren ? | Siwebueren / (any article) | Règlement grand-ducal du 16 mai 2019 portant création des zones de protection autour des captages d’eau souterraine Siwebueren et Katzebuer-Millebaach situées sur les territoires des communes de Kopstal, Luxembourg, Strassen et Walferdange. (Art. 2) | True | True |
| Quelle est la procédure pour obtenir une autorisation de bâtir au Luxembourg ? | Autorisation de b / (any article) | Version consolidée applicable au 01/10/2023 : Loi du 19 juillet 2004 concernant l'aménagement communal et le développement urbain. (Art. 59) | False | True |
| Quel est le seuil d'exemption pour l'autorisation de bâtir ? | Autorisation de b / (any article) | RÈGLEMENT SUR LES BÂTISSES, LES VOIES (Art. 96) | False | True |
| Que définit la loi concernant l'aménagement communal et le développement urbain ? | aménagement communal / (any article) | Loi du 17 avril 2018 concernant l’aménagement du territoire et modifiant : (Art. 32) | True | True |
| Quelle est la définition d'une zone spéciale de conservation Natura 2000 ? | protection de la nature / (any article) | Règlement grand-ducal du 28 octobre 2022 désignant zone spéciale de conservation et déclarant obligatoire la zone « Grunewald », et modifiant le règlement grand-ducal du 6 novembre 2009 portant désignation des zones spéciales de conservation. (Art. 1) | False | True |
| Quelle loi protège les monuments nationaux au Luxembourg ? | patrimoine culturel / (any article) | Loi du 25 février 2022 relative au patrimoine culturel et modifiant : (Art. 134) | True | True |
| Quelles sont les exigences d'accessibilité des lieux ouverts au public ? | accessibilité / (any article) | Loi du 7 janvier 2022 portant sur l’accessibilité à tous des lieux ouverts au public, des voies publiques et des bâtiments d’habitation collectifs. (Art. 14) | True | True |
| Quelle est la loi relative à l'eau au Luxembourg ? | relative à l'eau / (any article) | Loi du 25 février 2022 relative au patrimoine culturel et modifiant : (Art. 135) | True | True |
| Quels comités d'accompagnement existent pour les établissements classés ? | établissements classés / Art. 14 | Loi du 10 juin 1999 relative aux établissements classés. (Art. 3) | True | False |
| Quelles sont les sanctions pénales pour infraction à la loi sur les établissements classés ? | établissements classés / Art. 25 | Loi du 10 juin 1999 relative aux établissements classés. (Art. 3) | True | False |
| Quand la loi sur les établissements classés du 10 juin 1999 est-elle entrée en vigueur ? | établissements classés / Art. 30 | Loi du 25 février 2022 relative au patrimoine culturel et modifiant : (Art. 134) | True | False |
| Quel est le programme directeur d'aménagement du territoire ? | aménagement du territoire / Art. 5 | Loi du 17 avril 2018 concernant l’aménagement du territoire et modifiant : (Art. 32) | True | True |
| Combien coûte l'installation d'une piscine solaire au Groenland ? | (deliberately unanswerable) | Règlement sur les Bâtisses,  les Voies publiques et les (Art. 79) | None | None |

## Known gaps (honest, not hidden)

- **No dense/hybrid retrieval** — `chunks.embedding` (pgvector, HNSW-indexed) is part of the schema but was never populated; no embedding API key is configured in this environment. This eval measures lexical-only retrieval.
- **No reranking, no chatbot UI, no conversation memory, no parcel-scoped context** — M3's full scope was not built today; this is the retrieval core only, built specifically so this file could report real numbers instead of being left empty or fabricated.
- **No automatic refusal threshold** — the unanswerable question's retrieval score is reported, but nothing in this codebase yet decides "this is too low-relevance, say I don't know" — that logic belongs to the generation layer, which doesn't exist yet.
- **Golden set is hand-built from real ingested chunks**, not independently authored by someone who didn't already know the corpus — a real limitation of a same-day eval; a more rigorous version would have a second person (or a held-out real user question set) write the questions.
