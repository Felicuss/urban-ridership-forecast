package ru.mojarung.tramload;

import static com.tngtech.archunit.library.Architectures.layeredArchitecture;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

/** Границы слоёв: расчёт не зависит от Spring и от того, откуда пришли данные и куда уходит ответ. */
@AnalyzeClasses(packages = "ru.mojarung.tramload", importOptions = ImportOption.DoNotIncludeTests.class)
class ArchitectureTest {

	@ArchTest
	static final ArchRule domainIsPlainJava = noClasses().that()
		.resideInAPackage("..domain..")
		.should()
		.dependOnClassesThat()
		.resideInAnyPackage("org.springframework..", "reactor..", "tools.jackson..", "..application..",
				"..infrastructure..", "..api..");

	@ArchTest
	static final ArchRule layers = layeredArchitecture().consideringOnlyDependenciesInLayers()
		.withOptionalLayers(true)
		.layer("api").definedBy("..api..")
		.layer("application").definedBy("..application..")
		.layer("infrastructure").definedBy("..infrastructure..")
		.layer("domain").definedBy("..domain..")
		.whereLayer("api").mayNotBeAccessedByAnyLayer()
		.whereLayer("application").mayOnlyBeAccessedByLayers("api")
		.whereLayer("infrastructure").mayNotBeAccessedByAnyLayer();

}
