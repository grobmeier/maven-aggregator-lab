# SPDX-License-Identifier: Apache-2.0
"""Generate disposable marker POMs without starting Maven."""

from xml.dom.minidom import parseString


PLUGIN = """<groupId>maven.aggregator.lab</groupId>
<artifactId>aggregator-lab-maven-plugin</artifactId><version>1.0-SNAPSHOT</version>"""


def execution(name, phase, action, goal="probe"):
    return f"""<execution><id>{name}</id><phase>{phase}</phase>
<goals><goal>{goal}</goal></goals><configuration><action>{action}</action></configuration></execution>"""

def pom(body):
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
<modelVersion>4.0.0</modelVersion>{body}</project>
"""
    return "\n".join(line for line in parseString(xml).toprettyxml(indent="  ").splitlines() if line.strip()) + "\n"

def child_pom(name, parent, work, extra=""):
    return pom(f"""<parent><groupId>maven.aggregator.lab.acceptance</groupId><artifactId>{parent}</artifactId>
<version>1.0-SNAPSHOT</version></parent><artifactId>{name}</artifactId><packaging>pom</packaging>
<build><plugins><plugin>{PLUGIN}<executions>{work}{extra}</executions></plugin></plugins></build>""")

def create_nested(root, case):
    work = execution("contribute", "package", "work", "work")
    hooks = execution("start", "before:all", "start") + execution("cleanup", case.phase, "cleanup") + execution("aggregate", case.phase, "end")
    (root / "pom.xml").write_text(pom("""<groupId>maven.aggregator.lab.acceptance</groupId>
<artifactId>fixture-root</artifactId><version>1.0-SNAPSHOT</version><packaging>pom</packaging>
<modules><module>group</module><module>outside</module></modules>"""))
    group = root / "group"
    group.mkdir()
    (group / "pom.xml").write_text(pom(f"""<parent><groupId>maven.aggregator.lab.acceptance</groupId>
<artifactId>fixture-root</artifactId><version>1.0-SNAPSHOT</version></parent><artifactId>group</artifactId>
<packaging>pom</packaging><modules><module>a</module><module>b</module></modules>
<build><plugins><plugin>{PLUGIN}<inherited>false</inherited><executions>{hooks}</executions></plugin></plugins></build>"""))
    for name in ("a", "b"):
        (group / name).mkdir()
        (group / name / "pom.xml").write_text(child_pom(name, "group", work))
    (root / "outside").mkdir()
    (root / "outside/pom.xml").write_text(child_pom("outside", "fixture-root", work))

def create_fixture(root, case):
    root.mkdir(parents=True, exist_ok=False)
    if case.nested:
        create_nested(root, case)
        return
    start = "before:site" if case.lifecycle == "site" else "before:all"
    hooks = execution("start", start, "start")
    contribution_phase = "site" if case.lifecycle == "site" else "package"
    if case.single:
        hooks += execution("contribute", contribution_phase, "work", "work")
    # Cleanup is an observation marker. It does not create an aggregate or remove data.
    hooks += execution("cleanup", case.phase, "cleanup")
    hooks += execution("aggregate", case.phase, "end")
    inherited = "false"
    if case.inheritance:
        inherited = "true" if case.inheritance == "on" else "false"
        hooks = execution("start", "before:all", "start") + execution("finish", case.phase, "finish")
        hooks += execution("cleanup", case.phase, "cleanup").replace("<id>cleanup</id>", "<id>cleanup</id><inherited>false</inherited>")
        hooks += execution("aggregate", case.phase, "end").replace("<id>aggregate</id>", "<id>aggregate</id><inherited>false</inherited>")
    site_override = ""
    if case.lifecycle == "site":
        # Isolate lifecycle scheduling from rendering reports and downloading a site skin.
        site_override = """<plugin><artifactId>maven-site-plugin</artifactId><version>3.21.0</version>
<executions><execution><id>default-site</id><phase>none</phase></execution></executions></plugin>"""
    artifact = "fixture-single" if case.single else "fixture-root"
    modules = "" if case.single else "<modules><module>a</module><module>b</module></modules>"
    (root / "pom.xml").write_text(pom(f"""
<groupId>maven.aggregator.lab.acceptance</groupId><artifactId>{artifact}</artifactId>
<version>1.0-SNAPSHOT</version><packaging>pom</packaging>{modules}
<build><plugins><plugin>{PLUGIN}<inherited>{inherited}</inherited><executions>{hooks}</executions></plugin>
{site_override}</plugins></build>"""))
    if not case.single:
        for name in ("a", "b"):
            child = root / name
            child.mkdir()
            work = execution("contribute", contribution_phase, "work", "work")
            if case.lifecycle != "site":
                work += execution("fail-after-output", "after:verify", "fail-after-output", "work")
            extra = ""
            if case.inheritance == "explicit" and name == "a":
                extra = execution("child-start", "before:all", "start") + execution("child-finish", case.phase, "finish")
            (child / "pom.xml").write_text(child_pom(name, "fixture-root", work, extra))
