package ru.mojarung.tramload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class TramLoadApiApplication {

	public static void main(String[] args) {
		SpringApplication.run(TramLoadApiApplication.class, args);
	}

}
