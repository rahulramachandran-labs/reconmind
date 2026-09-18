from app.domain.protocol import DomainAdapter


def get_adapter(name: str) -> DomainAdapter:
    if name == "retail_recon":
        from app.domain.retail_recon import RetailReconAdapter

        return RetailReconAdapter()
    if name == "example_support_triage":
        from app.domain.example_support_triage import SupportTriageAdapter

        return SupportTriageAdapter()
    raise ValueError(f"unknown domain adapter {name}")
