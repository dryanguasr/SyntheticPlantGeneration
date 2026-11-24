"""The new adapter preserves actual model.train arguments and evaluator body."""
from pathlib import Path
import ast,unittest

ROOT=Path(__file__).resolve().parents[1]


def tree(name):return ast.parse((ROOT/'scripts'/name).read_text(encoding='utf-8'))


class Pilot115RecipeTests(unittest.TestCase):
    def test_training_call_is_exactly_the_previous_recipe(self):
        def call(name):
            return next(n for n in ast.walk(tree(name)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                        and isinstance(n.func.value,ast.Name) and n.func.value.id=='model' and n.func.attr=='train')
        self.assertEqual(ast.dump(call('train_reviewed_augmentation.py')),ast.dump(call('train_daylight_augmentation.py')))

    def test_evaluation_changes_only_the_pause_guard_argument(self):
        a=tree('evaluate_reviewed_augmentation.py');b=tree('evaluate_daylight_augmentation.py')
        class Normalize(ast.NodeTransformer):
            def visit_Call(self,node):
                self.generic_visit(node)
                if isinstance(node.func,ast.Name) and node.func.id=='generation_paused':node.args=[]
                return node
        functions=lambda t:[ast.dump(Normalize().visit(n)) for n in t.body if isinstance(n,ast.FunctionDef)]
        self.assertEqual(functions(a),functions(b))


if __name__=='__main__':unittest.main()
