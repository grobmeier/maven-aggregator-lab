// SPDX-License-Identifier: Apache-2.0
package maven.aggregator.lab;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugin.MojoFailureException;
import org.apache.maven.project.MavenProject;

/** Record lifecycle observations without a session extension or forked lifecycle. */
public final class ProbeMojo extends AbstractMojo {
    private File baseDirectory;
    private File eventRoot;
    private MavenProject project;
    private List<MavenProject> projects;
    private String action;
    private String contributors;
    private String failContributor;
    private String failureStage;

    @Override
    public void execute() throws MojoExecutionException, MojoFailureException {
        try {
            switch (action) {
                case "start", "cleanup", "finish":
                    record(action);
                    break;
                case "work":
                    if (project.getArtifactId().equals(failContributor) && !"after-output".equals(failureStage)) {
                        record("child-failure");
                        throw new MojoFailureException("DEMO_CHILD_FAILURE:" + project.getArtifactId());
                    }
                    Path contribution = baseDirectory.toPath().resolve("target/contribution.txt");
                    Files.createDirectories(contribution.getParent());
                    Files.writeString(contribution, project.getArtifactId() + "\n");
                    record("work");
                    break;
                case "fail-after-output":
                    if (project.getArtifactId().equals(failContributor) && "after-output".equals(failureStage)) {
                        record("child-failure");
                        throw new MojoFailureException("DEMO_CHILD_FAILURE:" + project.getArtifactId());
                    }
                    break;
                case "end":
                    collect();
                    break;
                default:
                    throw new MojoFailureException("DEMO_UNKNOWN_ACTION:" + action);
            }
        } catch (IOException exception) {
            throw new MojoExecutionException("Cannot write the acceptance fixture output.", exception);
        }
    }

    private void collect() throws IOException, MojoFailureException {
        record("end-attempt");
        Path root = eventRoot.toPath().toAbsolutePath().normalize();
        List<String> selected;
        if ("selected".equals(contributors) || "group".equals(contributors)) {
            selected = projects.stream()
                    .filter(p -> p.getModules().isEmpty())
                    .filter(p -> !"group".equals(contributors)
                            || p.getBasedir().toPath().toAbsolutePath().normalize()
                                    .startsWith(baseDirectory.toPath().toAbsolutePath().normalize()))
                    .map(p -> root.relativize(p.getBasedir().toPath().toAbsolutePath().normalize()).toString())
                    .map(p -> p.isEmpty() ? "." : p)
                    .sorted()
                    .toList();
        } else {
            selected = Arrays.asList(contributors.split(","));
        }
        List<String> missing = new ArrayList<>();
        for (String name : selected) {
            if (!Files.isRegularFile(root.resolve(name).resolve("target/contribution.txt"))) {
                missing.add(name);
            }
        }
        if (selected.isEmpty()) {
            throw new MojoFailureException("DEMO_NO_CONTRIBUTORS");
        }
        if (!missing.isEmpty()) {
            throw new MojoFailureException("DEMO_MISSING_CONTRIBUTIONS:" + String.join(",", missing));
        }
        try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(root.resolve("target/contributions.zip")))) {
            for (String name : selected) {
                zip.putNextEntry(new ZipEntry((".".equals(name) ? "self" : name) + "/contribution.txt"));
                Files.copy(root.resolve(name).resolve("target/contribution.txt"), zip);
                zip.closeEntry();
            }
        }
        record("end-success");
    }

    private void record(String event) throws IOException {
        Path target = eventRoot.toPath().resolve("target");
        Files.createDirectories(target);
        String line = event + ":" + project.getArtifactId();
        // Each append is one short write. The assertions accept either order for independent contributors.
        Files.writeString(target.resolve("events.txt"), line + "\n",
                StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        getLog().info("DEMO_EVENT:" + line);
    }
}
