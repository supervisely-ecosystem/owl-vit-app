from typing import List
import random

import torch
import numpy as np
import supervisely as sly
from supervisely.app.widgets import (
    Button,
    Card,
    Progress,
    Text,
    Empty,
    Container,
    Checkbox,
    Stepper,
    ClassesTable,
    ImageRegionSelector,
    ProjectThumbnail,
    RadioTabs,
    Input,
    GridGallery,
    InputNumber,
    Field,
    Progress,
)
import src.sly_globals as g

# sys.path.append(os.path.join(g.app_root_directory, "scenic"))
# from scenic.projects.owl_vit import models
# from scenic.projects.owl_vit.configs import clip_b32
# from src.model import prepare_image, prepare_text, get_predictions, draw_predictions
from transformers import OwlViTProcessor, OwlViTForObjectDetection
from transformers.image_utils import ImageFeatureExtractionMixin


# Use GPU if available
DEVICE = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
PREVIEW_IMAGES_INFOS = []
CURRENT_REF_IMAGE_INDEX = 0
REF_IMAGE_HISTORY = [CURRENT_REF_IMAGE_INDEX]

datasets_list = g.api.dataset.get_list(g.project_id)
image_info_list = []
for dataset in datasets_list:
    samples_count = (
        dataset.images_count
        if len(datasets_list) == 1
        else dataset.count * (100 - len(datasets_list)) / 100
    )
    image_info_list += random.sample(g.api.image.get_list(dataset.id), samples_count)
    if len(image_info_list) >= 1000:
        break

ref_image_info = image_info_list[CURRENT_REF_IMAGE_INDEX]


def get_image_path(image_name: str) -> str:
    for dataset in g.project_fs.datasets:
        if dataset.item_exists(image_name):
            return dataset.get_img_path(image_name)


######################
### Input project card
######################
project_preview = ProjectThumbnail(g.project_info)
progress_bar_download_data = Progress(hide_on_finish=False)
progress_bar_download_data.hide()
text_download_data = Text("Data has been successfully downloaded", status="success")
text_download_data.hide()
button_download_data = Button("Download")


@button_download_data.click
def download_data():
    try:
        if sly.fs.dir_exists(g.project_dir):
            sly.logger.info("Data already downloaded.")
        else:
            button_download_data.hide()
            progress_bar_download_data.show()
            sly.fs.mkdir(g.project_dir)
            with progress_bar_download_data(
                message=f"Processing images...", total=g.project_info.items_count
            ) as pbar:
                sly.Project.download(
                    api=g.api,
                    project_id=g.project_id,
                    dest_dir=g.project_dir,
                    batch_size=100,
                    progress_cb=pbar.update,
                    only_image_tags=False,
                    save_image_info=True,
                )
            sly.logger.info("Data successfully downloaded.")
        g.project_fs = sly.Project(g.project_dir, sly.OpenMode.READ)
        progress_bar_download_data.hide()
        button_download_data.hide()
        text_download_data.show()
        stepper.set_active_step(2)
    except Exception as e:
        sly.logger.info("Something went wrong.")
        progress_bar_download_data.hide()
        button_download_data.show()
        text_download_data.set("Data download failed", status="error")
        text_download_data.show()
        stepper.set_active_step(1)


data_card = Card(
    title="Input data",
    content=Container(
        [
            project_preview,
            progress_bar_download_data,
            text_download_data,
            button_download_data,
        ]
    ),
)


###########################################
### Model settings and results preview card
###########################################
text_prompt_textarea = Input(
    placeholder="Description of object, that you want to detect via NN model"
)
image_region_selector = ImageRegionSelector(
    image_info=ref_image_info, widget_width="500px", widget_height="500px"
)


@image_region_selector.bbox_changed
def bbox_updated(new_scaled_bbox):
    sly.logger.info(f"new_scaled_bbox: {new_scaled_bbox}")


previous_image_button = Button("Previous image", icon="zmdi zmdi-skip-previous")
next_image_button = Button("Next image", icon="zmdi zmdi-skip-next")
random_image_button = Button("New random image", icon="zmdi zmdi-refresh")
set_input_button = Button("Set model input")


@previous_image_button.click
def previous_image():
    CURRENT_REF_IMAGE_INDEX = REF_IMAGE_HISTORY[-2]
    image_region_selector.image_update(image_info_list[CURRENT_REF_IMAGE_INDEX])


@next_image_button.click
def next_image():
    CURRENT_REF_IMAGE_INDEX = REF_IMAGE_HISTORY[-1] + 1
    image_region_selector.image_update(image_info_list[CURRENT_REF_IMAGE_INDEX])


@random_image_button.click
def random_image():
    CURRENT_REF_IMAGE_INDEX = random.randint(0, len(image_info_list) - 1)
    REF_IMAGE_HISTORY.append(CURRENT_REF_IMAGE_INDEX)
    image_region_selector.image_update(image_info_list[CURRENT_REF_IMAGE_INDEX])


@set_input_button.click
def set_model_input():
    if model_settings_card.is_disabled() is False:
        model_settings_card.disable()
        model_input_tabs.disable()
        previous_image_button.disable()
        next_image_button.disable()
        random_image_button.disable()
        image_region_selector.disable()
        text_prompt_textarea.disable()
        set_input_button.text = "Change model input"
    else:
        model_settings_card.enable()
        model_input_tabs.enable()
        previous_image_button.enable()
        next_image_button.enable()
        random_image_button.enable()
        image_region_selector.enable()
        text_prompt_textarea.enable()
        set_input_button.text = "Set model input"


model_input_tabs = RadioTabs(
    titles=["Reference image", "Text prompt"],
    contents=[
        Container(
            [
                image_region_selector,
                previous_image_button,
                next_image_button,
                random_image_button,
            ]
        ),
        Container([text_prompt_textarea]),
    ],
    descriptions=[
        "Pick object by bounding box editing",
        "Describe object, that you want to detect",
    ],
)
model_settings_card = Card(
    title="Model settings",
    description="Configure input for model as text-prompt or as reference image",
    content=Container([model_input_tabs, set_input_button]),
)

grid_gallery = GridGallery(
    columns_number=g.COLUMNS_COUNT,
    annotations_opacity=0.5,
    show_opacity_slider=True,
    enable_zoom=False,
    sync_views=False,
    fill_rectangle=True,
)
for i in range(g.PREVIEW_IMAGES_COUNT):
    img_info = random.choice(image_info_list)
    PREVIEW_IMAGES_INFOS.append(img_info)
    grid_gallery.append(
        title=img_info.name,
        image_url=img_info.preview_url,
        column_index=int(i % g.COLUMNS_COUNT),
    )
confidence_threshhold_input = InputNumber(value=0.5, min=00.1, max=1, step=0.01)
nms_threshhold_input = InputNumber(value=1, min=0.01, max=1, step=0.01)
field_confidence_threshhold = Field(
    title="Confidence threshold",
    description="Threshold for the minimum confidence that a detection must have to be displayed (higher values mean fewer boxes will be shown):",
    content=confidence_threshhold_input,
)
field_nms_threshhold = Field(
    title="NMS threshold",
    description="Threshold for non-maximum suppression of overlapping boxes (higher values mean more boxes will be shown)",
    content=nms_threshhold_input,
)
update_preview_button = Button("Update preview")


@update_preview_button.click
def update_preview():
    confidence_threshhold = confidence_threshhold_input.get_value()
    nms_threshhold = nms_threshhold_input.get_value()

    model = OwlViTForObjectDetection.from_pretrained("google/owlvit-base-patch32")
    processor = OwlViTProcessor.from_pretrained("google/owlvit-base-patch32")
    model = model.to(DEVICE)
    model.eval()

    annotations_list = []
    for i, image_info in enumerate(PREVIEW_IMAGES_INFOS):
        image = sly.image.read(get_image_path(image_info.name))
        target_sizes = torch.Tensor([[image_info.height, image_info.width]]).to(DEVICE)
        new_annotation = sly.Annotation(img_size=(image_info.height, image_info.width))

        if model_input_tabs.get_active_tab() == "Reference image":
            selected_bbox = image_region_selector.scaled_bbox
            x0, y0, x1, y1 = np.array(selected_bbox).reshape(-1)
            query_image = sly.image.read(get_image_path(ref_image_info.name))
            query_image = query_image[y0:y1, x0:x1]
            inputs = processor(
                images=image, query_images=query_image, return_tensors="pt"
            ).to(DEVICE)

            with torch.no_grad():
                outputs = model.image_guided_detection(**inputs)

            outputs.logits = outputs.logits.cpu()
            outputs.target_pred_boxes = outputs.target_pred_boxes.cpu()

            results = processor.post_process_image_guided_detection(
                outputs=outputs,
                threshold=confidence_threshhold,
                nms_threshold=nms_threshhold,
                target_sizes=target_sizes,
            )
        else:
            text_queries = text_prompt_textarea.get_value().split(";")
            inputs = processor(text=text_queries, images=image, return_tensors="pt").to(
                DEVICE
            )

            with torch.no_grad():
                outputs = model(**inputs)

            results = processor.post_process(
                outputs=outputs,
                target_sizes=target_sizes,
                # threshold=confidence_threshhold,
                # nms_threshold=nms_threshhold,
            )

        scores = results[0]["scores"].cpu().detach().numpy()
        boxes = results[0]["boxes"].cpu().detach().numpy()
        labels = results[0]["labels"]
        if labels is None:
            labels = ["Object"] * len(boxes)
        else:
            labels = [text_queries[label] for label in labels]

        for score, box, label in zip(scores, boxes, labels):
            if score < confidence_threshhold:
                continue
            obj_class = sly.ObjClass(f"Object-{label}", sly.Rectangle)
            x0, y0, x1, y1 = box
            obj_label = sly.Label(sly.Rectangle(y0, x0, y1, x1), obj_class)
            new_annotation = new_annotation.add_label(obj_label)
        annotations_list.append(new_annotation)
        sly.logger.info(
            f"{i+1} image processed. {len(PREVIEW_IMAGES_INFOS) - (i+1)} images left."
        )

    grid_gallery.clean_up()
    for i, (image_info, annotation) in enumerate(
        zip(PREVIEW_IMAGES_INFOS, annotations_list)
    ):
        grid_gallery.append(
            image_url=image_info.preview_url,
            annotation=annotation,
            title=image_info.name,
            column_index=int(i % g.COLUMNS_COUNT),
        )


preview_card = Card(
    title="Preview results",
    description="Model prediction result preview",
    content=Container(
        [
            Container(
                [field_confidence_threshhold, field_nms_threshhold],
                direction="horizontal",
            ),
            grid_gallery,
            update_preview_button,
        ]
    ),
)

run_model_button = Button("Run model")
model_progress = Progress(message="Applying model..", hide_on_finish=False)
run_model_card = Card(
    title="Model apply progress",
    content=Container([run_model_button, model_progress]),
)

stepper = Stepper(
    widgets=[data_card, model_settings_card, preview_card, run_model_card]
)
app = sly.Application(layout=stepper)
