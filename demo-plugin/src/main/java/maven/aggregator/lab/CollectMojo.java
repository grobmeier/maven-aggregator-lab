// SPDX-License-Identifier: Apache-2.0
package maven.aggregator.lab;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugin.MojoFailureException;

/** See META-INF/maven/plugin.xml for the aggregator metadata and parameter injection. */
public final class CollectMojo extends AbstractMojo {
    private File baseDirectory;

    @Override
    public void execute() throws MojoExecutionException, MojoFailureException {
        Path root = baseDirectory.toPath();
        Path target = root.resolve("target");
        List<String> modules = List.of("library", "application");
        try {
            Files.createDirectories(target);
            Files.writeString(target.resolve("aggregate-attempts.txt"), "collect\n",
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            getLog().info("DEMO_AGGREGATION_ATTEMPT");
            List<String> missing = modules.stream()
                    .filter(module -> !Files.isRegularFile(jar(root, module)))
                    .toList();
            if (!missing.isEmpty()) {
                throw new MojoFailureException("DEMO_MISSING_CHILD_JARS: " + String.join(",", missing));
            }
            Path archive = target.resolve("child-jars.zip");
            try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(archive))) {
                for (String module : modules) {
                    Path input = jar(root, module);
                    zip.putNextEntry(new ZipEntry(module + "/" + input.getFileName()));
                    Files.copy(input, zip);
                    zip.closeEntry();
                }
            }
            getLog().info("DEMO_ZIP_CREATED: " + archive);
        } catch (IOException exception) {
            throw new MojoExecutionException("Cannot create the demo ZIP.", exception);
        }
    }

    private static Path jar(Path root, String module) {
        return root.resolve(module + "/target/" + module + "-1.0-SNAPSHOT.jar");
    }
}
