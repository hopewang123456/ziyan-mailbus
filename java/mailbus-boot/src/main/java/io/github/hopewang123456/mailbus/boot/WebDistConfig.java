package io.github.hopewang123456.mailbus.boot;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.resource.PathResourceResolver;

import java.io.IOException;
import java.util.List;

/**
 * Cockpit SPA hosting: serves the shared React build (web/dist) from the
 * monorepo and falls back to index.html for client-side routes — the java
 * serve becomes a drop-in cockpit host, same as the python one.
 */
@Configuration
public class WebDistConfig implements WebMvcConfigurer {

    /** welcome page does not consult custom file: locations — forward explicitly */
    @org.springframework.stereotype.Controller
    static class RootForward {
        @org.springframework.web.bind.annotation.GetMapping("/")
        public String root() {
            return "forward:/index.html";
        }
    }


    private final String distLocation;

    public WebDistConfig(org.springframework.core.env.Environment env) {
        String raw = env.getProperty("mailbus.web.dist", "../web/dist");
        java.nio.file.Path p = java.nio.file.Path.of(raw).toAbsolutePath().normalize();
        this.distLocation = p.toString();
        org.slf4j.LoggerFactory.getLogger(WebDistConfig.class)
                .info("cockpit dist: {} (exists={})", distLocation, java.nio.file.Files.isDirectory(p));
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/**")
                .addResourceLocations(java.nio.file.Path.of(distLocation).toUri().toString(), "classpath:/static/")
                .resourceChain(true)
                .addResolver(new PathResourceResolver() {
                    @Override
                    protected Resource getResource(String resourcePath, Resource location) throws IOException {
                        Resource requested = location.createRelative(resourcePath);
                        // API and actuator own their namespaces
                        if (resourcePath.startsWith("api/") || resourcePath.startsWith("actuator/")) {
                            return null;
                        }
                        return requested.exists() && requested.isReadable()
                                ? requested
                                : new ClassPathResource("/static/index.html").exists()
                                        ? new ClassPathResource("/static/index.html")
                                        : location.createRelative("index.html");
                    }
                });
    }
}
