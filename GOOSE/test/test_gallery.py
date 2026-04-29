import os
import kivy
from kivy.app import App
from kivy.lang import Builder

# Needs to be imported to register the Icons font correctly
from ui.icons import Icons
from ui.media_gallery import MediaGallery

class TestApp(App):
    def build(self):
        import os
        shared_kv = os.path.join(os.path.dirname(__file__), 'ui', 'kv', 'shared.kv')
        Builder.load_file(shared_kv)
        kv_path = os.path.join(os.path.dirname(__file__), 'ui', 'kv', 'media_gallery.kv')
        Builder.load_file(kv_path)
        g = MediaGallery()
        g.size_hint = (1, 1)

        import os
        rec_dir = os.path.join(os.getcwd(), 'recordings')
        if not os.path.exists(rec_dir):
            os.makedirs(rec_dir)
        for i in range(10):
            with open(os.path.join(rec_dir, f'test_vid_{i}.mp4'), 'w') as f:
                f.write('dummy')
                
        g.open()
        return g

if __name__ == '__main__':
    TestApp().run()
