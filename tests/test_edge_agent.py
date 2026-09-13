import pytest
from core.edge_diagnostic_agent import edge_agent

def test_edge_diagnostic_agent_fallback():
    # Test fallback when image doesn't exist
    result = edge_agent.audit_and_generate_prereport(
        image_path="non_existent_image.png",
        specialty="ginecologia",
        preliminary_findings="Útero en AVF de dimensiones conservadas."
    )

    assert result is not None
    assert "auditoria_calidad" in result
    assert "preinforme_estructurado" in result
    assert result["auditoria_calidad"]["calidad_tecnica"] in ["optima", "aceptable", "requiere_reiteracion"]
    assert len(result["preinforme_estructurado"]["hallazgos_principales"]) > 0
    print("\n[OK] Edge Diagnostic Agent Test Passed Successfully!")

if __name__ == "__main__":
    test_edge_diagnostic_agent_fallback()
