"""Additional companies flagged by research agents (2026-05-03).
Import this from jd_scraper.py to add to TARGETS on the fly via --expansion flag."""

EXPANSION_TARGETS = [
    # ───── Mid-size / niche Canadian banks (Priority 1 new finds) ─────
    {"name": "Fairstone Bank", "sector": "Mid Canadian Banks", "linkedin_slug": "fairstone-bank", "workday": None},
    {"name": "Home Trust", "sector": "Mid Canadian Banks", "linkedin_slug": "home-trust-company", "workday": None},
    {"name": "Haventree Bank", "sector": "Mid Canadian Banks", "linkedin_slug": "haventree-bank", "workday": None},
    {"name": "Laurentian Bank of Canada", "sector": "Mid Canadian Banks", "linkedin_slug": "laurentian-bank-of-canada", "workday": None},
    {"name": "Tangerine Bank", "sector": "Mid Canadian Banks", "linkedin_slug": "tangerine", "workday": None},
    {"name": "Amex Bank of Canada", "sector": "Mid Canadian Banks", "linkedin_slug": "american-express", "workday": None},
    {"name": "Rogers Bank", "sector": "Mid Canadian Banks", "linkedin_slug": "rogers-bank", "workday": None},
    {"name": "Canadian Tire Bank", "sector": "Mid Canadian Banks", "linkedin_slug": "canadian-tire-corporation", "workday": None},
    {"name": "Manulife Bank", "sector": "Mid Canadian Banks", "linkedin_slug": "manulife-bank", "workday": None},
    {"name": "RFA Bank of Canada", "sector": "Mid Canadian Banks", "linkedin_slug": "rfa-capital", "workday": None},

    # ───── Additional Canadian insurers & mortgage insurers ─────
    {"name": "Fairfax Financial Holdings", "sector": "Canadian Insurers", "linkedin_slug": "fairfax-financial-holdings", "workday": None},
    {"name": "ivari", "sector": "Canadian Insurers", "linkedin_slug": "ivari", "workday": None},
    {"name": "Foresters Financial", "sector": "Canadian Insurers", "linkedin_slug": "foresters-financial", "workday": None},
    {"name": "Empire Life", "sector": "Canadian Insurers", "linkedin_slug": "empire-life", "workday": None},
    {"name": "Equitable Life of Canada", "sector": "Canadian Insurers", "linkedin_slug": "equitable-life-of-canada", "workday": None},
    {"name": "Aviva Canada", "sector": "Canadian Insurers", "linkedin_slug": "aviva-canada", "workday": None},
    {"name": "Co-operators", "sector": "Canadian Insurers", "linkedin_slug": "co-operators", "workday": None},
    {"name": "Wawanesa Insurance", "sector": "Canadian Insurers", "linkedin_slug": "wawanesa-insurance", "workday": None},
    {"name": "Northbridge Financial", "sector": "Canadian Insurers", "linkedin_slug": "northbridge-financial", "workday": None},
    {"name": "Munich Re Canada", "sector": "Canadian Insurers", "linkedin_slug": "munich-re", "workday": None},
    {"name": "Swiss Re Canada", "sector": "Canadian Insurers", "linkedin_slug": "swiss-re", "workday": None},
    {"name": "Trisura Group", "sector": "Canadian Insurers", "linkedin_slug": "trisura-group", "workday": None},
    {"name": "Canada Guaranty", "sector": "Canadian Insurers", "linkedin_slug": "canada-guaranty", "workday": None},
    {"name": "Sagen MI Canada", "sector": "Canadian Insurers", "linkedin_slug": "sagen", "workday": None},

    # ───── Mortgage originators / non-bank lenders ─────
    {"name": "MCAP Financial", "sector": "Mortgage Lenders", "linkedin_slug": "mcap", "workday": None},
    {"name": "First National Financial", "sector": "Mortgage Lenders", "linkedin_slug": "first-national-financial-lp", "workday": None},
    {"name": "CMLS Financial", "sector": "Mortgage Lenders", "linkedin_slug": "cmls-financial", "workday": None},
    {"name": "Element Fleet Management", "sector": "Non-Bank Lenders", "linkedin_slug": "element-fleet-management", "workday": None},
    {"name": "Ford Credit Canada", "sector": "Non-Bank Lenders", "linkedin_slug": "ford-motor-company", "workday": None},
    {"name": "Hyundai Capital Canada", "sector": "Non-Bank Lenders", "linkedin_slug": "hyundai-capital-canada", "workday": None},
    {"name": "Toyota Financial Services Canada", "sector": "Non-Bank Lenders", "linkedin_slug": "toyota-financial-services", "workday": None},

    # ───── Additional asset managers / fund admins ─────
    {"name": "Fiera Capital", "sector": "Canadian Asset Managers", "linkedin_slug": "fiera-capital", "workday": None},
    {"name": "Beutel Goodman", "sector": "Canadian Asset Managers", "linkedin_slug": "beutel-goodman", "workday": None},
    {"name": "Burgundy Asset Management", "sector": "Canadian Asset Managers", "linkedin_slug": "burgundy-asset-management", "workday": None},
    {"name": "1832 Asset Management", "sector": "Canadian Asset Managers", "linkedin_slug": "1832-asset-management", "workday": None},
    {"name": "Purpose Investments", "sector": "Canadian Asset Managers", "linkedin_slug": "purpose-investments", "workday": None},
    {"name": "Horizons ETFs / Global X", "sector": "Canadian Asset Managers", "linkedin_slug": "global-x-etfs-canada", "workday": None},
    {"name": "Franklin Templeton Canada", "sector": "US & Global Asset Managers", "linkedin_slug": "franklin-templeton", "workday": None},

    # ───── Hedge funds / private credit ─────
    {"name": "Polar Asset Management", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "polar-asset-management", "workday": None},
    {"name": "RPIA", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "rp-investment-advisors", "workday": None},
    {"name": "Algonquin Capital", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "algonquin-capital-corporation", "workday": None},
    {"name": "Lawrence Park Asset Management", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "lawrence-park-asset-management", "workday": None},
    {"name": "Waratah Capital Advisors", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "waratah-advisors", "workday": None},
    {"name": "Sagard Holdings", "sector": "Private Credit", "linkedin_slug": "sagard-holdings", "workday": None},
    {"name": "Northleaf Capital Partners", "sector": "Private Credit", "linkedin_slug": "northleaf-capital-partners", "workday": None},
    {"name": "KingSett Capital", "sector": "Private Credit", "linkedin_slug": "kingsett-capital", "workday": None},
    {"name": "Ninepoint Partners", "sector": "Private Credit", "linkedin_slug": "ninepoint-partners-lp", "workday": None},
    {"name": "Trez Capital", "sector": "Private Credit", "linkedin_slug": "trez-capital-group", "workday": None},
    {"name": "Romspen Investment Corporation", "sector": "Private Credit", "linkedin_slug": "romspen-investment-corporation", "workday": None},
    {"name": "Antares Capital", "sector": "Private Credit", "linkedin_slug": "antares-capital", "workday": None},
    {"name": "Third Eye Capital", "sector": "Private Credit", "linkedin_slug": "third-eye-capital", "workday": None},

    # ───── Fund admin / custody ─────
    {"name": "CIBC Mellon", "sector": "Fund Admin/Custody", "linkedin_slug": "cibc-mellon", "workday": None},
    {"name": "RBC Investor Services", "sector": "Fund Admin/Custody", "linkedin_slug": "rbc-investor-services", "workday": None},
    {"name": "Citco Fund Services", "sector": "Fund Admin/Custody", "linkedin_slug": "citco", "workday": None},
    {"name": "SEI Investments Canada", "sector": "Fund Admin/Custody", "linkedin_slug": "sei-investments", "workday": None},
    {"name": "Apex Group", "sector": "Fund Admin/Custody", "linkedin_slug": "apex-group-ltd", "workday": None},
    {"name": "MUFG Investor Services", "sector": "Fund Admin/Custody", "linkedin_slug": "mufg-investor-services", "workday": None},

    # ───── Exchange / market infrastructure ─────
    {"name": "TMX Group", "sector": "Market Infrastructure", "linkedin_slug": "tmx-group", "workday": None},
    {"name": "Fundserv", "sector": "Market Infrastructure", "linkedin_slug": "fundserv", "workday": None},
    {"name": "Finastra", "sector": "Analytics & Risk Vendors", "linkedin_slug": "finastra", "workday": None},
    {"name": "FIS Global", "sector": "Analytics & Risk Vendors", "linkedin_slug": "fis", "workday": None},
    {"name": "Broadridge", "sector": "Analytics & Risk Vendors", "linkedin_slug": "broadridge", "workday": None},
    {"name": "DTCC", "sector": "Market Infrastructure", "linkedin_slug": "dtcc", "workday": None},
    {"name": "Cboe Canada", "sector": "Market Infrastructure", "linkedin_slug": "cboe-global-markets", "workday": None},

    # ───── Additional analytics/risk vendors ─────
    {"name": "SAS Canada", "sector": "Analytics & Risk Vendors", "linkedin_slug": "sas", "workday": None},
    {"name": "Wolters Kluwer", "sector": "Analytics & Risk Vendors", "linkedin_slug": "wolters-kluwer", "workday": None},
    {"name": "Nasdaq", "sector": "Analytics & Risk Vendors", "linkedin_slug": "nasdaq", "workday": None},
    {"name": "Moody's Corporation", "sector": "Analytics & Risk Vendors", "linkedin_slug": "moodys-corporation", "workday": None, "successfactors": "https://careers.moodys.com"},
    {"name": "Qontigo", "sector": "Analytics & Risk Vendors", "linkedin_slug": "qontigo", "workday": None},
    {"name": "Quantifi", "sector": "Analytics & Risk Vendors", "linkedin_slug": "quantifi", "workday": None},
    {"name": "ION Group", "sector": "Analytics & Risk Vendors", "linkedin_slug": "ion-group", "workday": None},
    {"name": "Murex", "sector": "Analytics & Risk Vendors", "linkedin_slug": "murex", "workday": None},

    # ───── Vendor-platform / risk-analytics (PRIMARY lane, elevated 2026-05-30) ─────
    {"name": "SS&C Technologies (Algorithmics)", "sector": "Analytics & Risk Vendors", "linkedin_slug": "ss-c-technologies", "workday": None},
    {"name": "Numerix", "sector": "Analytics & Risk Vendors", "linkedin_slug": "numerix", "workday": None},
    {"name": "Prometeia", "sector": "Analytics & Risk Vendors", "linkedin_slug": "prometeia", "workday": None},
    {"name": "Clearwater Analytics", "sector": "Analytics & Risk Vendors", "linkedin_slug": "clearwater-analytics", "workday": None},

    # ───── Regulators & Crown corps ─────
    {"name": "OSFI", "sector": "Regulators & Crown", "linkedin_slug": "office-of-the-superintendent-of-financial-institutions", "workday": None},
    {"name": "Bank of Canada", "sector": "Regulators & Crown", "linkedin_slug": "bank-of-canada", "workday": None, "successfactors": "https://careers.bankofcanada.ca"},
    {"name": "CDIC", "sector": "Regulators & Crown", "linkedin_slug": "canada-deposit-insurance-corporation", "workday": None},
    {"name": "FSRA Ontario", "sector": "Regulators & Crown", "linkedin_slug": "financial-services-regulatory-authority-of-ontario-fsra-", "workday": None},
    {"name": "Ontario Securities Commission", "sector": "Regulators & Crown", "linkedin_slug": "ontario-securities-commission", "workday": None},
    {"name": "CMHC", "sector": "Regulators & Crown", "linkedin_slug": "cmhc-schl", "workday": None, "successfactors": "https://careers.cmhc-schl.gc.ca"},
    {"name": "EDC", "sector": "Regulators & Crown", "linkedin_slug": "export-development-canada", "workday": None},
    {"name": "BDC", "sector": "Regulators & Crown", "linkedin_slug": "bdc", "workday": None},
    {"name": "CIRO", "sector": "Regulators & Crown", "linkedin_slug": "canadian-investment-regulatory-organization", "workday": None},
    {"name": "Infrastructure Ontario", "sector": "Regulators & Crown", "linkedin_slug": "infrastructure-ontario", "workday": None},

    # ───── Fintech with senior finance roles ─────
    {"name": "Wealthsimple", "sector": "Fintech", "linkedin_slug": "wealthsimple", "workday": None},
    {"name": "Questrade Financial Group", "sector": "Fintech", "linkedin_slug": "questrade", "workday": None},
    {"name": "Interac", "sector": "Fintech", "linkedin_slug": "interac-corp-", "workday": None},
    {"name": "Moneris", "sector": "Fintech", "linkedin_slug": "moneris-solutions", "workday": None},
    {"name": "Nuvei", "sector": "Fintech", "linkedin_slug": "nuvei", "workday": None},
    {"name": "Neo Financial", "sector": "Fintech", "linkedin_slug": "neo-financial", "workday": None},
    {"name": "Payments Canada", "sector": "Fintech", "linkedin_slug": "payments-canada", "workday": None},

    # ───── US fintech / HF with Toronto presence (Greenhouse-hosted) ─────
    # Discovered empirically 2026-05-04 via auto-probe of Greenhouse boards.
    {"name": "Stripe", "sector": "Fintech", "linkedin_slug": "stripe", "workday": None,
     "greenhouse": "stripe"},
    {"name": "Affirm", "sector": "Fintech", "linkedin_slug": "affirm", "workday": None,
     "greenhouse": "affirm"},
    {"name": "Robinhood", "sector": "Fintech", "linkedin_slug": "robinhood", "workday": None,
     "greenhouse": "robinhood"},
    {"name": "Point72", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "point72", "workday": None,
     "greenhouse": "point72"},

    # ═════════════════════════════════════════════════════════════════════
    # Gap-fill 2026-06-15 — verified Toronto-present employers found missing in
    # a coverage audit (asset managers, hedge funds, foreign banks, CFA-centric
    # asset owners). A wrong LinkedIn slug just yields no hits (safe to add);
    # re-check any that return zero after the next full scrape.
    # ═════════════════════════════════════════════════════════════════════

    # ── Asset managers — insurance general-account / LDI / institutional
    #    (strongest fit: maps to his Ortec/Moody's pension-ALM + LDI core) ──
    {"name": "SLC Management", "sector": "Canadian Asset Managers", "linkedin_slug": "slc-management", "workday": None},
    {"name": "Manulife Investment Management", "sector": "Canadian Asset Managers", "linkedin_slug": "manulife-investment-management", "workday": None},
    {"name": "CIBC Asset Management", "sector": "Canadian Asset Managers", "linkedin_slug": "cibc-asset-management", "workday": None},
    {"name": "Desjardins Global Asset Management", "sector": "Canadian Asset Managers", "linkedin_slug": "desjardins-global-asset-management", "workday": None},
    {"name": "Addenda Capital", "sector": "Canadian Asset Managers", "linkedin_slug": "addenda-capital-inc", "workday": None},
    {"name": "Russell Investments Canada", "sector": "Canadian Asset Managers", "linkedin_slug": "russell-investments", "workday": None},
    {"name": "Mawer Investment Management", "sector": "Canadian Asset Managers", "linkedin_slug": "mawer-investment-management", "workday": None},

    # ── Hedge funds / liquid alts that hire Toronto-based investment risk ──
    {"name": "Verition Fund Management", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "verition-fund-management", "workday": None},
    {"name": "Marret Asset Management", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "marret-asset-management-inc-", "workday": None},
    {"name": "Hillsdale Investment Management", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "hillsdale-investment-management", "workday": None},
    {"name": "Anson Funds", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "anson-group-of-funds", "workday": None},
    {"name": "Balyasny Asset Management", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "balyasny-asset-management", "workday": None},
    {"name": "Citadel", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "citadel", "workday": None},
    {"name": "Sprott", "sector": "Hedge Funds / Alt AM", "linkedin_slug": "sprott-inc-", "workday": None},

    # ── Private / alternative credit (credit-risk + FI fit) ──
    {"name": "Onex (Onex Credit)", "sector": "Private Credit", "linkedin_slug": "onex", "workday": None},
    {"name": "Canso Investment Counsel", "sector": "Private Credit", "linkedin_slug": "canso-investment-counsel-ltd-", "workday": None},
    {"name": "Blackstone Credit", "sector": "Private Credit", "linkedin_slug": "blackstone", "workday": None},
    {"name": "Barings", "sector": "Private Credit", "linkedin_slug": "barings", "workday": None},

    # ── Foreign / US banks with a Toronto markets / treasury / risk footprint ──
    {"name": "Bank of America", "sector": "US Banks (Toronto)", "linkedin_slug": "bank-of-america", "workday": None},
    {"name": "MUFG Bank (Canada)", "sector": "US Banks (Toronto)", "linkedin_slug": "mufg", "workday": None},
    {"name": "UBS", "sector": "US Banks (Toronto)", "linkedin_slug": "ubs", "workday": None},
    {"name": "Macquarie Group", "sector": "US Banks (Toronto)", "linkedin_slug": "macquarie-group", "workday": None},
    {"name": "SMBC", "sector": "US Banks (Toronto)", "linkedin_slug": "smbc-group", "workday": None},
    {"name": "Mizuho", "sector": "US Banks (Toronto)", "linkedin_slug": "mizuho", "workday": None},
    {"name": "PNC (Canada)", "sector": "US Banks (Toronto)", "linkedin_slug": "pnc", "workday": None},
    {"name": "Natixis CIB", "sector": "US Banks (Toronto)", "linkedin_slug": "natixis", "workday": None},
    # Montreal-hubbed risk/model-validation teams (Toronto markets office only) —
    # lower priority for a no-relocation candidate, but some roles are Toronto/remote.
    {"name": "Societe Generale", "sector": "US Banks (Toronto)", "linkedin_slug": "societe-generale", "workday": None},
    {"name": "BNP Paribas", "sector": "US Banks (Toronto)", "linkedin_slug": "bnp-paribas", "workday": None},

    # ── CFA-centric institutional asset OWNERS + OCIO + rating (Toronto) ──
    {"name": "WSIB", "sector": "Canadian Pension Funds", "linkedin_slug": "wsib", "workday": None},
    {"name": "University Pension Plan", "sector": "Canadian Pension Funds", "linkedin_slug": "university-pension-plan", "workday": None},
    {"name": "UTAM", "sector": "Canadian Pension Funds", "linkedin_slug": "university-of-toronto-asset-management-corporation", "workday": None},
    {"name": "OPG Pension Fund", "sector": "Canadian Pension Funds", "linkedin_slug": "ontario-power-generation", "workday": None},
    {"name": "Ontario Pension Board", "sector": "Canadian Pension Funds", "linkedin_slug": "ontario-pension-board", "workday": None},
    {"name": "Trans-Canada Capital", "sector": "Canadian Pension Funds", "linkedin_slug": "transcanadacapital", "workday": None},
    {"name": "Fitch Ratings", "sector": "Analytics & Risk Vendors", "linkedin_slug": "fitch-ratings", "workday": None},
]
