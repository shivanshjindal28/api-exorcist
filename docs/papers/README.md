# Source papers

The ten peer-reviewed works cited in [`../literature-review.md`](../literature-review.md).

Every entry below was verified against the DBLP computer science bibliography for
exact title, author list, venue, year and DOI before being cited.

## Present in this folder (9 of 10)

Each was confirmed by extracting page 1 and matching the title and author list against
the DBLP record.

| File | Paper |
|---|---|
| `01-caivano-2023-dead-methods.pdf` | Caivano et al., *On the spread and evolution of dead methods in Java desktop applications*, EMSE 28(3) 2023 |
| `03-bushong-2021-static-analysis-msa-reconstruction.pdf` | Bushong et al., *Using Static Analysis to Address Microservice Architecture Reconstruction*, ASE 2021 |
| `04-ma-2019-graph-based-microservice-analysis.pdf` | Ma et al., *Graph-based and scenario-driven microservice analysis, retrieval, and testing*, FGCS 100 2019 |
| `05-abdelfattah-2023-microservice-dependency-matrix.pdf` | Abdelfattah & Cerný, *The Microservice Dependency Matrix*, ESOCC 2023 |
| `06-dellimmagine-2023-kubehound.pdf` | Dell'Immagine et al., *KubeHound: Detecting Microservices' Security Smells in Kubernetes Deployments*, Future Internet 15(7) 2023 |
| `07-ponce-2024-beyond-security.pdf` | Ponce et al., *Beyond Security: Understanding the Multiple Impacts of Security Smells for Microservices*, CLEIej 27(2) 2024 |
| `08-lundberg-lee-2017-shap.pdf` | Lundberg & Lee, *A Unified Approach to Interpreting Model Predictions*, NIPS 2017 |
| `09-gaspar-2024-xai-ids-lime-shap.pdf` | Gaspar et al., *Explainable AI for Intrusion Detection Systems: LIME and SHAP Applicability on Multi-Layer Perceptron*, IEEE Access 12 2024 |
| `10-scheitle-2018-certificate-transparency.pdf` | Scheitle et al., *The Rise of Certificate Transparency and Its Implications on the Internet Ecosystem*, IMC 2018 |

### Full-text verification status

Three of the four papers flagged in §10 of the review have now been read in full.

| Paper | Outcome |
|---|---|
| [1] Caivano | Verified. 23 applications, 1,587 commits confirmed. Three findings now do real work in §2, including *"dead methods are rarely revived"* — the evidence underwriting Safe Kill |
| [3] Bushong | Verified, **and it forced a correction.** A three-page method paper with no evaluation section. Claims of a "measured result" and a three-phase extraction pipeline were not in it and have been removed |
| [4] Ma | Verified, **and stronger than written.** They implement their Service Dependency Graph in Neo4j 3.1.1 and evaluate it from ten to hundreds of microservices. Our backend choice is precedent, not inference |
| [9] Gaspar | Verified. The SHAP cost limitation is real but **qualitative** — no overhead figure is reported, so none is claimed |

## Still to retrieve (1)

Save as `02-cassieri-2023-deprecated-api-usages.pdf`
> P. Cassieri, S. Romano, and G. Scanniello, "On deprecated API usages: an exploratory
> study of top-starred projects on GitHub," in *Proc. PROFES*, 2023.
> DOI: [10.1007/978-3-031-49266-2_29](https://doi.org/10.1007/978-3-031-49266-2_29) · Springer LNCS

Available through the NMIMS library subscription — use the library proxy or the campus
network, then save it into this folder under that filename.

**Why this one still matters.** [2] is the paper that explains the single
misclassification in our evaluation: `POST /v1/kyc/aadhaar/ekyc` is genuinely
deprecated but classified active, because it is the one deprecated endpoint whose team
never set the OpenAPI flag. §2 of the review states that deprecation markers are
"inconsistently applied and inconsistently acted upon", which the abstract supports.
Confirm the specific consistency rate of replacement messages before quoting any
figure — and correct anything the full text does not bear out, as happened with [3].

## Note on access

Only openly licensed copies belong in this folder. Do not use paper-piracy mirrors —
a capstone that cites material obtained that way is a problem you do not want, and
your library subscription makes it unnecessary.
