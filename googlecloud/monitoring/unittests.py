import os
from unittest import TestCase
from gke_cpu import get_projects


class Test(TestCase):
    def test_get_projects(self):
        projects = get_projects(os.environ['project_id_glob'])
        self.assertGreater(len(projects), 0)
        print(f"found project ID {projects[0]}")
