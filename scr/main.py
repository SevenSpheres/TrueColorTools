import time
import numpy as np
import PySimpleGUI as sg
from PIL import Image, ImageDraw
import plotly.graph_objects as go
import scr.cmf as cmf
import scr.gui as gui
import scr.filters as filters
import scr.calculations as calc
import scr.data_import as di
import scr.strings as tr
import scr.table_generator as tg
import scr.experimental


def export(rgb):
    lst = []
    mx = 0
    for i in rgb:
        lst.append(str(i))
        l = len(lst[-1])
        if l > mx:
            mx = l
    w = 8 if mx < 8 else mx+1
    return "".join([i.ljust(w) for i in lst])

def launch_window(lang, debug):
    objectsDB, refsDB = {}, {} # initial loading became too long with separate json5 database files
    tagsDB = []
    default_tag = 'featured'

    T2_preview = (256, 128)
    T2_area = T2_preview[0]*T2_preview[1]
    T4_text_colors = ("#A3A3A3", "#FFFFFF")
    window = sg.Window("True Color Tools", gui.generate_layout(T2_preview, T4_text_colors, lang), finalize=True)
    T2_vis = 3  # current number of visible image bands
    T2_num = 10 # max number of image bands, ~ len(window["T2_frames"])

    T1_preview = window["T1_graph"].DrawCircle((48, 46), 42, fill_color="black", line_color="white")
    T4_preview = window["T4_graph"].DrawCircle((48, 46), 42, fill_color="black", line_color="white")

    T1_fig = go.Figure()
    T1_events = ["T1_list", "T1_gamma", "T1_srgb", "T1_br_mode0", "T1_br_mode1", "T1_br_mode2", "T1_interp0", "T1_interp1", "T1_slider", "T1_bit_num", "T1_rnd_num"]
    br_modes = ["chromaticity", "albedo 0.5", "albedo"]

    for i in range(T2_vis, T2_num):
        window["T2_band"+str(i)].update(visible=False)


    # Window events loop

    names = []
    while True:
        event, values = window.Read()

        # Global window events

        if event == sg.WIN_CLOSED or event == tr.gui_exit[lang]:
            break

        elif event in tr.lang_list[lang]:
            for lng, lst in tr.langs.items(): # determine language to translate
                if event in lst:
                    lang = lng
                    break
            window = gui.translate(window, T2_num, lang)
            window["T1_list"].update(values=tuple(di.obj_dict(objectsDB, values["T1_tags"], lang).keys()))
        
        elif event == tr.ref[lang]:
            to_show = ''
            for key, value in refsDB.items():
                to_show += f'"{key}": {value[0]}\n'
                for info in value[1:]:
                    to_show += info + '\n'
                to_show += '\n'
            sg.popup_scrolled(to_show, title=event, size=(150, 25))
        
        elif event == tr.note[lang]:
            notes = []
            for note, translation in tr.notes.items():
                notes.append(f"{note} {translation[lang]}")
            sg.popup("\n".join(notes), title=event)
        
        elif event == tr.gui_info[lang]:
            sg.popup(f'{tr.link}\n{tr.auth_info[lang]}', title=event)
        
        elif event.endswith('database'): # global loading of spectra database
            objectsDB, refsDB = di.import_DBs(['spectra'])
            tagsDB = di.tag_list(objectsDB)
            window['T1_tagsN'].update(visible=True)
            window['T1_tags'].update(default_tag, values=tagsDB, visible=True)
            window['T3_tagsN'].update(visible=True)
            window['T3_tags'].update(default_tag, values=tagsDB, visible=True)
            window['T1_list'].update(values=tuple(di.obj_dict(objectsDB, default_tag, lang).keys()), visible=True)
            window['T1_database'].metadata=False
            window['T1_database'].update(tr.gui_update[lang])
            window['T3_database'].metadata=False
            window['T3_database'].update(tr.gui_update[lang])
        
        # ------------ Events in the tab "Spectra" ------------

        elif event.startswith("T1"):

            if event in T1_events and values["T1_list"] != []:
                T1_name = values["T1_list"][0]
                T1_nm = cmf.xyz_nm if values["T1_srgb"] else cmf.rgb_nm
                for i in range(3):
                    if values["T1_br_mode"+str(i)]:
                        T1_mode = br_modes[i]

                # Spectral data import and processing
                T1_spectrum = objectsDB[di.obj_dict(objectsDB, "all", lang)[T1_name]]
                T1_albedo = 0
                if "albedo" not in T1_spectrum:
                    if T1_mode == "albedo":
                        T1_mode = "chromaticity"
                    T1_spectrum |= {"albedo": False}
                elif type(T1_spectrum["albedo"]) != bool:
                    T1_albedo = T1_spectrum["albedo"]
                T1_spectrum = calc.standardize_photometry(T1_spectrum)
                
                # Spectrum interpolation
                try:
                    T1_sun = T1_spectrum['sun']
                except KeyError:
                    T1_sun = False
                T1_curve = calc.polator(T1_spectrum["nm"], T1_spectrum["br"], T1_nm, T1_albedo, values["T1_interp1"], desun=T1_sun)
                
                # Color calculation
                try:
                    T1_phase = 0 if "star" in T1_spectrum["tags"] else values["T1_slider"]
                except Exception:
                    T1_phase = values["T1_slider"]
                T1_rgb = calc.to_rgb(
                    T1_name, T1_curve, mode=T1_mode,
                    albedo = T1_spectrum["albedo"] or T1_albedo,
                    phase=T1_phase,
                    exp_bit=int(values["T1_bit_num"]), 
                    gamma=values["T1_gamma"], 
                    rnd=int(values["T1_rnd_num"]),
                    srgb=values["T1_srgb"]
                )
                T1_rgb_show = calc.to_rgb(
                    T1_name, T1_curve, mode=T1_mode,
                    albedo = T1_spectrum["albedo"] or T1_albedo,
                    phase=T1_phase,
                    gamma=values["T1_gamma"],
                    srgb=values["T1_srgb"],
                    html=True
                )

                # Output
                window["T1_graph"].TKCanvas.itemconfig(T1_preview, fill=T1_rgb_show)
                window["T1_rgb"].update(T1_rgb)
                window["T1_hex"].update(T1_rgb_show)
            
            elif event == "T1_tags":
                window["T1_list"].update(tuple(di.obj_dict(objectsDB, values["T1_tags"], lang).keys()))
            
            elif event == "T1_add" and values["T1_list"] != []:
                names.append(values["T1_list"][0])
                T1_fig.add_trace(go.Scatter(
                    x = T1_nm,
                    y = T1_curve,
                    name = values["T1_list"][0],
                    line = dict(color=T1_rgb_show, width=4)
                    ))
            
            elif event == "T1_plot":
                if len(names) == 1:
                    T1_title_text = tr.single_title_text[lang] + names[0]
                else:
                    T1_title_text = tr.batch_title_text[lang] + ", ".join(names)
                T1_fig.update_layout(title=T1_title_text, xaxis_title=tr.xaxis_text[lang], yaxis_title=tr.yaxis_text[lang])
                T1_fig.show()
            
            elif event == "T1_export":
                T1_export = "\n" + "\t".join(tr.gui_col[lang]) + "\n" + "_" * 36
                T1_nm = cmf.xyz_nm if values["T1_srgb"] else cmf.rgb_nm
                
                # Spectrum processing
                for name_1, name_0 in di.obj_dict(objectsDB, values["T1_tags"], lang).items():
                    T1_spectrum = objectsDB[name_0]
                    for i in range(3):
                        if values["T1_br_mode"+str(i)]:
                            T1_mode = br_modes[i]
                    T1_albedo = 0
                    if "albedo" not in T1_spectrum:
                        if T1_mode == "albedo":
                            T1_mode = "chromaticity"
                        T1_spectrum |= {"albedo": False}
                    elif type(T1_spectrum["albedo"]) != bool:
                        T1_albedo = T1_spectrum["albedo"]
                    T1_spectrum = calc.standardize_photometry(T1_spectrum)
                    
                    # Spectrum interpolation
                    try:
                        T1_sun = T1_spectrum['sun']
                    except KeyError:
                        T1_sun = False
                    T1_curve = calc.polator(T1_spectrum["nm"], T1_spectrum["br"], T1_nm, T1_albedo, values["T1_interp1"], desun=T1_sun)

                    # Color calculation
                    T1_rgb = calc.to_rgb(
                        name_0, T1_curve, mode=T1_mode,
                        albedo = T1_spectrum["albedo"] or T1_albedo,
                        exp_bit=int(values["T1_bit_num"]), 
                        gamma=values["T1_gamma"], 
                        rnd=int(values["T1_rnd_num"]),
                        srgb=values["T1_srgb"]
                    )

                    # Output
                    T1_export += f'\n{export(T1_rgb)}\t{name_1}'

                sg.popup_scrolled(T1_export, title=tr.gui_results[lang], size=(72, 32), font=("Consolas", 10))
        
        # ------------ Events in the tab "Images" ------------

        elif event.startswith("T2"):

            if event == "T2_single":
                window["T2_browse"].update(disabled=not values["T2_single"])
                window["T2_path"].update(disabled=not values["T2_single"])
                for i in range(T2_num):
                    window["T2_browse"+str(i)].update(disabled=values["T2_single"])
                    window["T2_path"+str(i)].update(disabled=values["T2_single"])
                    window["T2_exposure"+str(i)].update(disabled=values["T2_single"])
                if values["T2_single"]:
                    T2_vis = 3
                    for i in range(T2_num):
                        window["T2_band"+str(i)].update(visible=False)
                    for i in range(3):
                        window["T2_band"+str(i)].update(visible=True)

            elif event == "T2_filterset":
                window["T2_filter"].update(disabled=not values["T2_filterset"])
                for i in range(T2_num):
                    window["T2_filter"+str(i)].update(disabled=not values["T2_filterset"])
                    window["T2_wavelength"+str(i)].update(disabled=values["T2_filterset"])

            elif event == "T2_filter":
                for i in range(T2_num):
                    window["T2_filter"+str(i)].update(values=filters.get_filters(values["T2_filter"]))

            elif event in ["T2_filter"+str(i) for i in range(T2_num)]:
                i = event[-1]
                window["T2_wavelength"+i].update(filters.get_param(values["T2_filter"], values["T2_filter"+i], "L_mean"))

            elif event == "T2_folder":
                window["T2_process"].update(disabled=False)
            
            elif event == "T2_+":
                window["T2_band"+str(T2_vis)].update(visible=True)
                T2_vis += 1
            
            elif event == "T2_-":
                window["T2_band"+str(T2_vis-1)].update(visible=False)
                T2_vis -= 1
            
            window["T2_+"].update(disabled=values["T2_single"] or not 2 <= T2_vis < T2_num)
            window["T2_-"].update(disabled=values["T2_single"] or not 2 < T2_vis <= T2_num)
            for i in range(T2_num):
                window["T2_filterN"+str(i)].update(text_color=("#A3A3A3", "#FFFFFF")[values["T2_filterset"]])
                window["T2_wavelengthN"+str(i)].update(text_color=("#A3A3A3", "#FFFFFF")[not values["T2_filterset"]])
                window["T2_exposureN"+str(i)].update(text_color=("#A3A3A3", "#FFFFFF")[not values["T2_single"]])
            
            input_data = {"gamma": values["T2_gamma"], "srgb": values["T2_srgb"], "desun": values["T2_desun"], "nm": []}
            
            T2_preview_status = True
            if values["T2_single"]:
                if values["T2_path"] == "":
                    T2_preview_status = False
            else:
                for i in range(T2_vis):
                    if values["T2_path"+str(i)] == "":
                        T2_preview_status = False
                        break
            if values["T2_filterset"]:
                for i in range(T2_vis):
                    if values["T2_filter"+str(i)]:
                        try:
                            input_data["nm"].append(filters.get_param(values["T2_filter"], values["T2_filter"+str(i)], "L_mean"))
                        except KeyError:
                            window["T2_filter"+str(i)].update([])
                    else:
                        T2_preview_status = False
                        break
            else:
                for i in range(T2_vis):
                    if values["T2_wavelength"+str(i)].replace(".", "").isnumeric():
                        input_data["nm"].append(float(values["T2_wavelength"+str(i)]))
                    else:
                        T2_preview_status = False
                        break
            if not all(a > b for a, b in zip(input_data["nm"][1:], input_data["nm"])): # increasing check
                T2_preview_status = False
            window["T2_preview"].update(disabled=not T2_preview_status)
            window["T2_process"].update(disabled=not T2_preview_status) if values["T2_folder"] != "" else window["T2_process"].update(disabled=True)
            
            if event in ("T2_preview", "T2_process"):

                T2_time = time.monotonic()
                T2_load = []

                if values["T2_single"]:
                    T2_rgb_img = Image.open(values["T2_path"])
                    if T2_rgb_img.mode == "P": # NameError if color is indexed
                        T2_rgb_img = T2_rgb_img.convert("RGB")
                        sg.Print('Note: image converted from "P" (indexed color) mode to "RGB"')
                    if event == "T2_preview":
                        T2_ratio = T2_rgb_img.width / T2_rgb_img.height
                        T2_rgb_img = T2_rgb_img.resize((int(np.sqrt(T2_area*T2_ratio)), int(np.sqrt(T2_area/T2_ratio))), resample=Image.Resampling.HAMMING)
                    if len(T2_rgb_img.getbands()) == 3:
                        r, g, b = T2_rgb_img.split()
                        a = None
                    elif len(T2_rgb_img.getbands()) == 4:
                        r, g, b, a = T2_rgb_img.split()
                    for i in [b, g, r]:
                        T2_load.append(np.array(i))
                else:
                    T2_exposures = [float(values["T2_exposure"+str(i)]) for i in range(T2_vis)]
                    T2_max_exposure = max(T2_exposures)
                    for i in range(T2_vis):
                        T2_bw_img = Image.open(values["T2_path"+str(i)])
                        if T2_bw_img.mode not in ("L", "I", "F"): # image should be b/w
                            sg.Print(f'Note: image of band {i+1} converted from "{T2_bw_img.mode}" mode to "L"')
                            T2_bw_img = T2_bw_img.convert("L")
                        if i == 0:
                            T2_size = T2_bw_img.size
                        else:
                            if T2_size != T2_bw_img.size:
                                sg.Print(f'Note: image of band {i+1} resized from {T2_bw_img.size} to {T2_size}')
                                T2_bw_img = T2_bw_img.resize(T2_size)
                        if event == "T2_preview":
                            T2_ratio = T2_bw_img.width / T2_bw_img.height
                            T2_bw_img = T2_bw_img.resize((int(np.sqrt(T2_area*T2_ratio)), int(np.sqrt(T2_area/T2_ratio))), resample=Image.Resampling.HAMMING)
                        T2_load.append(np.array(T2_bw_img) / T2_exposures[i] * T2_max_exposure)
                
                T2_data = np.array(T2_load, "int64")
                T2_l, T2_h, T2_w = T2_data.shape
                
                if values["T2_autoalign"]:
                    T2_data = scr.experimental.autoalign(T2_data, debug)
                    T2_l, T2_h, T2_w = T2_data.shape
                
                T2_data = T2_data.astype("float32")
                T2_max = T2_data.max()
                if values["T2_makebright"]:
                    T2_data *= 65500 / T2_max
                    T2_input_bit = 16
                    T2_input_depth = 65535
                else:
                    T2_input_bit = 16 if T2_max > 255 else 8
                    T2_input_depth = 65535 if T2_max > 255 else 255
                #T2_data = np.clip(T2_data, 0, T2_input_depth)
                
                # Calibration of maps by spectrum (legacy)
                #if info["calib"]:
                #    if "br" in info:
                #        br = np.array(info["br"])
                #        obl = 0
                #    elif "ref" in info:
                #        ref = calc.standardize_photometry(db.objects[info["ref"]])
                #        albedo = ref["albedo"] if "albedo" in ref else 0
                #        br = calc.get_points(bands, ref["nm"], ref["br"], albedo)
                #        obl = ref["obl"] if "obl" in ref else 0
                #    for u in range(n): # calibration cycles
                #        for y in range(h):
                #            for layer in range(l):
                #                if np.sum(data[layer][y]) != 0:
                #                    calib[layer][0].append(np.sum(data[layer][y]) / np.count_nonzero(data[layer][y]))
                #                    calib[layer][1].append(k(np.pi * (0.5 - (y + 0.5) / h), obl))
                #        for layer in range(l):
                #            avg = np.average(calib[layer][0], weights=calib[layer][1])
                #            color = depth * br[layer]
                #            data[layer] = data[layer] * color / avg

                T2_fast = True if values["T2_interp1"] else False
                T2_nm = cmf.xyz_nm if input_data["srgb"] else cmf.rgb_nm
                T2_img = Image.new("RGB", (T2_w, T2_h), (0, 0, 0))
                T2_draw = ImageDraw.Draw(T2_img)
                T2_counter = 0
                T2_px_num = T2_w*T2_h
                
                if values["T2_plotpixels"]:
                    T2_fig = go.Figure()
                    T2_fig.update_layout(title=tr.map_title_text[lang], xaxis_title=tr.xaxis_text[lang], yaxis_title=tr.yaxis_text[lang])

                sg.Print(f'\n{round(time.monotonic() - T2_time, 3)} seconds for loading, autoalign and creating output templates\n')
                sg.Print(f'{time.strftime("%H:%M:%S")} 0%')

                T2_time = time.monotonic()
                T2_get_spectrum_time = 0
                T2_calc_polator_time = 0
                T2_calc_rgb_time = 0
                T2_draw_point_time = 0
                T2_plot_pixels_time = 0
                T2_progress_bar_time = 0

                for x in range(T2_w):
                    for y in range(T2_h):

                        T2_temp_time = time.monotonic_ns()
                        T2_spectrum = T2_data[:, y, x]
                        T2_get_spectrum_time += time.monotonic_ns() - T2_temp_time

                        if np.sum(T2_spectrum) > 0:
                            T2_name = f'({x}; {y})'

                            T2_temp_time = time.monotonic_ns()
                            T2_curve = calc.polator(input_data["nm"], list(T2_spectrum), T2_nm, fast=T2_fast, desun=input_data["desun"])
                            T2_calc_polator_time += time.monotonic_ns() - T2_temp_time

                            T2_temp_time = time.monotonic_ns()
                            T2_rgb = calc.to_rgb(T2_name, T2_curve, mode="albedo", albedo=True, inp_bit=T2_input_bit, exp_bit=8, gamma=input_data["gamma"])
                            T2_calc_rgb_time += time.monotonic_ns() - T2_temp_time

                            T2_temp_time = time.monotonic_ns()
                            T2_draw.point((x, y), T2_rgb)
                            T2_draw_point_time += time.monotonic_ns() - T2_temp_time

                            if values["T2_plotpixels"]:
                                T2_temp_time = time.monotonic_ns()
                                if x % 32 == 0 and y % 32 == 0:
                                    T2_fig.add_trace(go.Scatter(
                                        x = T2_nm,
                                        y = T2_curve,
                                        name = T2_name,
                                        line = dict(color="rgb"+str(T2_rgb), width=2)
                                        ))
                                T2_plot_pixels_time += time.monotonic_ns() - T2_temp_time
                        
                        T2_temp_time = time.monotonic_ns()
                        T2_counter += 1
                        if T2_counter % 2048 == 0:
                            try:
                                sg.Print(f'{time.strftime("%H:%M:%S")} {round(T2_counter/T2_px_num * 100)}%, {round(T2_counter/(time.monotonic()-T2_time))} px/sec')
                            except ZeroDivisionError:
                                sg.Print(f'{time.strftime("%H:%M:%S")} {round(T2_counter/T2_px_num * 100)}% (ZeroDivisionError)')
                        T2_progress_bar_time += time.monotonic_ns() - T2_temp_time
                
                T2_end_time = time.monotonic()
                sg.Print(f'\n{round(T2_end_time - T2_time, 3)} seconds for color processing, where:')
                sg.Print(f'\t{T2_get_spectrum_time / 1e9} for getting spectrum')
                sg.Print(f'\t{T2_calc_polator_time / 1e9} for inter/extrapolating')
                sg.Print(f'\t{T2_calc_rgb_time / 1e9} for color calculating')
                sg.Print(f'\t{T2_draw_point_time / 1e9} for pixel drawing')
                sg.Print(f'\t{T2_plot_pixels_time / 1e9} for adding spectrum to plot')
                sg.Print(f'\t{T2_progress_bar_time / 1e9} for progress bar')
                sg.Print(f'\t{round(T2_end_time-T2_time-(T2_get_spectrum_time+T2_calc_polator_time+T2_calc_rgb_time+T2_draw_point_time+T2_plot_pixels_time+T2_progress_bar_time)/1e9, 3)} sec for other (time, black-pixel check)')
                
                if values["T2_plotpixels"]:
                    T2_fig.show()
                if event == "T2_preview":
                    window["T2_image"].update(data=gui.convert_to_bytes(T2_img))
                else:
                    T2_img.save(f'{values["T2_folder"]}/TCT_{time.strftime("%Y-%m-%d_%H-%M")}.png')
            
                #except Exception as e:
                #    print(e)
        
        # ------------ Events in the tab "Table" ------------

        elif event.startswith("T3"):
            
            if values["T3_folder"] != "":
                window["T3_process"].update(disabled=False)

            if event == "T3_process":

                # Database preprocessing
                for i in range(3):
                    if values["T3_br_mode"+str(i)]:
                        T3_mode0 = br_modes[i]
                tg.generate_table(objectsDB, tagsDB, T3_mode0, values["T3_srgb"], values["T3_gamma"], values["T3_folder"], values["T3_extension"], lang)

        
        # ------------ Events in the tab "Blackbody & Redshifts" ------------
        
        elif event.startswith("T4"):
            
            if event == "T4_maxtemp_num":
                window["T4_slider1"].update(range=(0, int(values["T4_maxtemp_num"])))
            
            else:
                if event == "T4_surfacebr":
                    window["T4_scale"].update(text_color=T4_text_colors[values["T4_surfacebr"]])
                    window["T4_slider4"].update(disabled=not values["T4_surfacebr"])
                
                T4_mode = "albedo" if values["T4_surfacebr"] else "chromaticity"
                T4_nm = cmf.xyz_nm if values["T4_srgb"] else cmf.rgb_nm
                T4_curve = calc.blackbody_redshift(T4_nm, values["T4_slider1"], values["T4_slider2"], values["T4_slider3"])
                if values["T4_surfacebr"]:
                    try:
                        T4_curve /= calc.mag2intensity(values["T4_slider4"])
                    except np.core._exceptions.UFuncTypeError:
                        pass
                T4_name = f'{values["T4_slider1"]} {values["T4_slider2"]} {values["T4_slider3"]}'
                T4_rgb = calc.to_rgb(
                    T4_name, T4_curve, mode=T4_mode,
                    albedo=values["T4_surfacebr"],
                    exp_bit=int(values["T4_bit_num"]),
                    gamma=values["T4_gamma"],
                    rnd=int(values["T4_rnd_num"]),
                    srgb=values["T4_srgb"]
                )
                T4_rgb_show = calc.to_rgb(
                    T4_name, T4_curve, mode=T4_mode,
                    albedo=values["T4_surfacebr"],
                    gamma=values["T4_gamma"],
                    srgb=values["T4_srgb"],
                    html=True
                )
            
                # Output
                window["T4_graph"].TKCanvas.itemconfig(T4_preview, fill=T4_rgb_show)
                window["T4_rgb"].update(T4_rgb)
                window["T4_hex"].update(T4_rgb_show)

    window.close()